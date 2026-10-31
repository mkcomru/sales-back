## Scheduled Reminder

You have a scheduled task to follow up with this customer.

**Reminder:** {{ title }}
{% if description %}
**Details:** {{ description }}
{% endif %}

{% if order_context %}
**Current Order State:**
- Stage: {{ order_context.stage_name }}
- Fields: {{ order_context.fields | tojson }}
{% endif %}

{% if recent_summary %}
**Recent Conversation:**
{{ recent_summary }}
{% endif %}

---

**Your task:** Follow up with the customer naturally. Reference the conversation history and reminder context to craft a relevant, personalized message. Do not mention that this is an automated reminder.
