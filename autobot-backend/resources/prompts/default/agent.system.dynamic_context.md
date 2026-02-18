## Current Session Context

**Session Information:**
- Session ID: {{ session_id }}
- Date: {{ current_date }}
- Time: {{ current_time }}

**User Context:**
- User: {{ user_name | default("User") }}
- Role: {{ user_role | default("Standard User") }}

**Available Tools:**
{% if available_tools %}
{{ available_tools | join(", ") }}
{% else %}
All standard AutoBot tools
{% endif %}

**Recent Context:**
{% if recent_context %}
{{ recent_context }}
{% else %}
No recent context available
{% endif %}

**Additional Parameters:**
{% if additional_params %}
{% for key, value in additional_params.items() %}
- {{ key }}: {{ value }}
{% endfor %}
{% endif %}
