import json

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import AssistantConversation, AssistantMessage, AssistantFeedback
from .serializers import (
    AssistantChatRequestSerializer,
    AssistantChatResponseSerializer,
    AssistantConversationListSerializer,
    AssistantMessageSerializer,
    AssistantConversationMessagesResponseSerializer,
    AssistantConversationRenameSerializer,
    AssistantFeedbackCreateSerializer,
)
from .services.prompt_builder import build_system_prompt, build_user_prompt
from .services.llm_client import HuggingFaceLLMClient
from .services.context_fetcher import fetch_incident_context, fetch_site_context


def _clean_json_text(text: str) -> str:
    text = text.strip()

    if text.startswith("```json"):
        text = text[len("```json"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    return text


def _parse_model_output(raw_answer: str) -> dict:
    raw_answer = _clean_json_text(raw_answer)

    try:
        parsed = json.loads(raw_answer)
        if isinstance(parsed, dict):
            return {
                "answer": parsed.get("answer", ""),
                "suggestedActions": parsed.get("suggestedActions", []),
                "emailDraft": parsed.get("emailDraft"),
                "rcaDraft": parsed.get("rcaDraft"),
            }
    except Exception:
        pass

    try:
        inner = json.loads(raw_answer)
        if isinstance(inner, str):
            inner = _clean_json_text(inner)
            parsed_inner = json.loads(inner)
            if isinstance(parsed_inner, dict):
                return {
                    "answer": parsed_inner.get("answer", ""),
                    "suggestedActions": parsed_inner.get("suggestedActions", []),
                    "emailDraft": parsed_inner.get("emailDraft"),
                    "rcaDraft": parsed_inner.get("rcaDraft"),
                }
    except Exception:
        pass

    return {
        "answer": raw_answer,
        "suggestedActions": [],
        "emailDraft": None,
        "rcaDraft": None,
    }


def _build_conversation_title(message: str, mode: str) -> str:
    clean = " ".join(message.strip().split())
    if not clean:
        return f"{mode.title()} conversation"

    if len(clean) <= 72:
        return clean

    return clean[:69].rstrip() + "..."


def _get_request_user_info(request):
    token_user = request.user
    user_id = getattr(token_user, "id", None) or getattr(token_user, "user_id", None)
    user_email = getattr(token_user, "email", "") or ""

    return {
        "user_id": user_id,
        "user_email": user_email,
    }


def _get_or_create_conversation(request, conversation_id, mode, message):
    user_info = _get_request_user_info(request)

    if not user_info["user_id"]:
        raise ValueError("Authenticated token does not contain user_id.")

    if conversation_id:
        conversation = AssistantConversation.objects.filter(
            id=conversation_id,
            user_id=user_info["user_id"],
            is_archived=False,
        ).first()

        if not conversation:
            raise ValueError("Conversation not found or not accessible.")

        if conversation.mode != mode:
            conversation.mode = mode
            conversation.updated_at = timezone.now()
            conversation.save(update_fields=["mode", "updated_at"])

        return conversation, False

    conversation = AssistantConversation.objects.create(
        title=_build_conversation_title(message, mode),
        user_id=user_info["user_id"],
        user_email=user_info["user_email"],
        mode=mode,
        metadata={},
        last_message_at=timezone.now(),
    )
    return conversation, True


def _serialize_conversation_list_item(conversation):
    latest_message = conversation.messages.order_by("-created_at").first()
    latest_preview = ""
    if latest_message and latest_message.content:
        latest_preview = latest_message.content[:140]

    return {
        "id": conversation.id,
        "title": conversation.title,
        "mode": conversation.mode,
        "is_archived": conversation.is_archived,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "last_message_at": conversation.last_message_at,
        "message_count": getattr(conversation, "message_count", conversation.messages.count()),
        "latest_message_preview": latest_preview,
    }


def _serialize_message(message):
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "mode": message.mode,
        "content": message.content,
        "context_snapshot": message.context_snapshot or {},
        "parsed_payload": message.parsed_payload or {},
        "model_name": message.model_name or "",
        "prompt_version": message.prompt_version or "v1",
        "is_training_candidate": message.is_training_candidate,
        "created_at": message.created_at,
    }


def _get_recent_history_messages(conversation, limit=8):
    return list(
        conversation.messages.order_by("-created_at")[:limit]
    )[::-1]


def _format_history_for_prompt(messages):
    if not messages:
        return ""

    lines = []
    for item in messages:
        role = item.role.upper()
        content = (item.content or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")

    if not lines:
        return ""

    return (
        "\n\nConversation history:\n"
        + "\n".join(lines)
        + "\n\nUse this history only as context. Prioritize the latest user request."
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def assistant_chat(request):
    serializer = AssistantChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    validated = serializer.validated_data
    message = validated["message"]
    mode = validated["mode"]
    conversation_id = validated.get("conversationId")
    context = validated.get("context", {})

    incident_id = context.get("incidentId")
    selected_site = context.get("selectedSite")

    incident_context = fetch_incident_context(request, incident_id)
    site_context = fetch_site_context(request, selected_site)

    enriched_context = {
        **context,
        "incidentData": incident_context,
        "siteData": site_context,
    }

    try:
        with transaction.atomic():
            conversation, _ = _get_or_create_conversation(
                request=request,
                conversation_id=conversation_id,
                mode=mode,
                message=message,
            )

            recent_history = _get_recent_history_messages(conversation, limit=8)
            history_block = _format_history_for_prompt(recent_history)

            AssistantMessage.objects.create(
                conversation=conversation,
                role="user",
                mode=mode,
                content=message,
                context_snapshot=enriched_context,
                parsed_payload={},
                model_name="",
                prompt_version="v1",
                is_training_candidate=False,
            )

            system_prompt = build_system_prompt(mode)
            user_prompt = build_user_prompt(message, mode, enriched_context)

            if history_block:
                user_prompt = f"{user_prompt}{history_block}"

            client = HuggingFaceLLMClient()
            raw_answer = client.chat(system_prompt, user_prompt).strip()
            parsed = _parse_model_output(raw_answer)

            response_payload = {
                "conversationId": conversation.id,
                "answer": parsed.get("answer", ""),
                "suggestedActions": parsed.get("suggestedActions", []),
                "emailDraft": parsed.get("emailDraft"),
                "rcaDraft": parsed.get("rcaDraft"),
            }

            assistant_message = AssistantMessage.objects.create(
                conversation=conversation,
                role="assistant",
                mode=mode,
                content=response_payload["answer"],
                context_snapshot=enriched_context,
                parsed_payload={
                    "suggestedActions": response_payload["suggestedActions"],
                    "emailDraft": response_payload["emailDraft"],
                    "rcaDraft": response_payload["rcaDraft"],
                    "raw_answer": raw_answer,
                },
                model_name=client.model,
                prompt_version="v1",
                is_training_candidate=False,
            )

            response_payload["assistantMessageId"] = assistant_message.id

            conversation.last_message_at = timezone.now()
            conversation.updated_at = timezone.now()
            conversation.save(update_fields=["last_message_at", "updated_at"])

            response_serializer = AssistantChatResponseSerializer(data=response_payload)
            response_serializer.is_valid(raise_exception=True)

            return Response(response_serializer.data, status=status.HTTP_200_OK)

    except ValueError as e:
        return Response(
            {
                "error": "Assistant request failed",
                "details": str(e),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        return Response(
            {
                "error": "Assistant request failed",
                "details": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def assistant_conversation_list(request):
    user_info = _get_request_user_info(request)

    if not user_info["user_id"]:
        return Response(
            {"error": "Authenticated token does not contain user_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversations = (
        AssistantConversation.objects.filter(
            user_id=user_info["user_id"],
            is_archived=False,
        )
        .annotate(message_count=Count("messages"))
        .order_by("-updated_at")
    )

    payload = [_serialize_conversation_list_item(conversation) for conversation in conversations]
    serializer = AssistantConversationListSerializer(payload, many=True)

    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def assistant_conversation_messages(request, conversation_id):
    user_info = _get_request_user_info(request)

    if not user_info["user_id"]:
        return Response(
            {"error": "Authenticated token does not contain user_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversation = (
        AssistantConversation.objects.filter(
            id=conversation_id,
            user_id=user_info["user_id"],
            is_archived=False,
        )
        .annotate(message_count=Count("messages"))
        .first()
    )

    if not conversation:
        return Response(
            {"error": "Conversation not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    messages = conversation.messages.order_by("created_at")
    response_payload = {
        "conversation": _serialize_conversation_list_item(conversation),
        "messages": [_serialize_message(message) for message in messages],
    }

    serializer = AssistantConversationMessagesResponseSerializer(data=response_payload)
    serializer.is_valid(raise_exception=True)

    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def assistant_conversation_rename(request, conversation_id):
    user_info = _get_request_user_info(request)

    if not user_info["user_id"]:
        return Response(
            {"error": "Authenticated token does not contain user_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = AssistantConversationRenameSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    conversation = AssistantConversation.objects.filter(
        id=conversation_id,
        user_id=user_info["user_id"],
        is_archived=False,
    ).first()

    if not conversation:
        return Response(
            {"error": "Conversation not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    conversation.title = serializer.validated_data["title"]
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=["title", "updated_at"])

    conversation.message_count = conversation.messages.count()
    payload = _serialize_conversation_list_item(conversation)
    response_serializer = AssistantConversationListSerializer(payload)

    return Response(response_serializer.data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def assistant_conversation_archive(request, conversation_id):
    user_info = _get_request_user_info(request)

    if not user_info["user_id"]:
        return Response(
            {"error": "Authenticated token does not contain user_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversation = AssistantConversation.objects.filter(
        id=conversation_id,
        user_id=user_info["user_id"],
        is_archived=False,
    ).first()

    if not conversation:
        return Response(
            {"error": "Conversation not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    conversation.is_archived = True
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=["is_archived", "updated_at"])

    return Response(
        {
            "id": conversation.id,
            "is_archived": conversation.is_archived,
            "message": "Conversation archived successfully.",
        },
        status=status.HTTP_200_OK,
    )

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def assistant_conversation_delete(request, conversation_id):
    """
    Soft delete for PFE safety:
    keep conversation/messages in DB, but hide them from active history.

    Idempotent behavior:
    - If conversation is already archived, still return 204.
    - If conversation does not exist or belongs to another user, return 404.
    """
    user_info = _get_request_user_info(request)

    if not user_info["user_id"]:
        return Response(
            {"error": "Authenticated token does not contain user_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversation = AssistantConversation.objects.filter(
        id=conversation_id,
        user_id=user_info["user_id"],
    ).first()

    if not conversation:
        return Response(
            {"error": "Conversation not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not conversation.is_archived:
        conversation.is_archived = True
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["is_archived", "updated_at"])

    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def assistant_message_feedback(request, message_id):
    user_info = _get_request_user_info(request)

    if not user_info["user_id"]:
        return Response(
            {"error": "Authenticated token does not contain user_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = AssistantFeedbackCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    message = AssistantMessage.objects.filter(
        id=message_id,
        role="assistant",
        conversation__user_id=user_info["user_id"],
    ).first()

    if not message:
        return Response(
            {"error": "Assistant message not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    feedback = AssistantFeedback.objects.create(
        message=message,
        user_id=user_info["user_id"],
        user_email=user_info["user_email"],
        rating=serializer.validated_data["rating"],
        notes=serializer.validated_data.get("notes", ""),
        corrected_answer=serializer.validated_data.get("corrected_answer", ""),
        use_for_finetuning=serializer.validated_data.get("use_for_finetuning", False),
    )

    if feedback.use_for_finetuning:
        message.is_training_candidate = True
        message.save(update_fields=["is_training_candidate"])

    return Response(
        {
            "id": feedback.id,
            "message_id": message.id,
            "rating": feedback.rating,
            "use_for_finetuning": feedback.use_for_finetuning,
            "created_at": feedback.created_at,
        },
        status=status.HTTP_201_CREATED,
    )