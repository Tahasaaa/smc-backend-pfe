from rest_framework import serializers


class AssistantContextSerializer(serializers.Serializer):
    technology = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    incidentId = serializers.IntegerField(required=False, allow_null=True)
    selectedSite = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    kpis = serializers.ListField(required=False, child=serializers.JSONField(), default=list)
    rca = serializers.JSONField(required=False, allow_null=True)
    emailDraft = serializers.JSONField(required=False, allow_null=True)


class AssistantChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField()
    mode = serializers.ChoiceField(
        choices=["general", "incident", "rca", "email", "monitoring", "map"]
    )
    conversationId = serializers.IntegerField(required=False, allow_null=True)
    context = AssistantContextSerializer(required=False, default=dict)


class AssistantChatResponseSerializer(serializers.Serializer):
    conversationId = serializers.IntegerField()
    assistantMessageId = serializers.IntegerField(required=False)
    answer = serializers.CharField()
    suggestedActions = serializers.ListField(child=serializers.CharField(), default=list)
    emailDraft = serializers.JSONField(required=False, allow_null=True)
    rcaDraft = serializers.JSONField(required=False, allow_null=True)


class AssistantConversationListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    mode = serializers.CharField()
    is_archived = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    last_message_at = serializers.DateTimeField(allow_null=True)
    message_count = serializers.IntegerField()
    latest_message_preview = serializers.CharField(allow_blank=True)


class AssistantMessageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    conversation_id = serializers.IntegerField()
    role = serializers.CharField()
    mode = serializers.CharField()
    content = serializers.CharField()
    context_snapshot = serializers.JSONField()
    parsed_payload = serializers.JSONField()
    model_name = serializers.CharField(allow_blank=True, required=False)
    prompt_version = serializers.CharField(allow_blank=True, required=False)
    is_training_candidate = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class AssistantConversationMessagesResponseSerializer(serializers.Serializer):
    conversation = AssistantConversationListSerializer()
    messages = AssistantMessageSerializer(many=True)

class AssistantConversationRenameSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, allow_blank=False)

    def validate_title(self, value):
        clean = " ".join(value.strip().split())
        if not clean:
            raise serializers.ValidationError("Conversation title cannot be empty.")
        return clean


class AssistantFeedbackCreateSerializer(serializers.Serializer):
    rating = serializers.ChoiceField(choices=[1, -1])
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    corrected_answer = serializers.CharField(required=False, allow_blank=True, default="")
    use_for_finetuning = serializers.BooleanField(required=False, default=False)