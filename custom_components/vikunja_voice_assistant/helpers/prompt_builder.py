import json
from datetime import datetime, timezone, timedelta


def build_task_creation_messages(
    task_description,
    projects,
    labels,
    default_due_date: str = "none",
    voice_correction: bool = False,
    users=None,
    enable_user_assignment: bool = False,
):
    """Build OpenAI chat messages to create a Vikunja task from a description.

    Returns a list of messages suitable for the OpenAI Chat Completions API.
    """
    project_names = [
        {"id": p.get("id"), "name": p.get("title")} for p in (projects or [])
    ]
    label_names = [
        {"id": label_obj.get("id"), "name": label_obj.get("title")}
        for label_obj in (labels or [])
        if isinstance(label_obj, dict) and label_obj.get("id") is not None
    ]

    # Current date/time context
    now = datetime.now(timezone.utc)
    current_timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    current_date = now.strftime("%Y-%m-%d")

    # Default due date helper values
    tomorrow = (
        (now + timedelta(days=1))
        .replace(hour=12, minute=0, second=0, microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    end_of_week = (
        (now + timedelta(days=7))
        .replace(hour=17, minute=0, second=0, microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    end_of_month = (
        (now + timedelta(days=30))
        .replace(hour=17, minute=0, second=0, microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    default_due_date_instructions = ""
    if default_due_date != "none":
        default_due_date_value = ""
        if default_due_date == "tomorrow":
            default_due_date_value = tomorrow
        elif default_due_date == "end_of_week":
            default_due_date_value = end_of_week
        elif default_due_date == "end_of_month":
            default_due_date_value = end_of_month

        default_due_date_instructions = f"""
        IMPORTANT DEFAULT DUE DATE RULE:
        - ONLY apply the default due date ({default_due_date_value}) when BOTH conditions are met:
          1. The user does NOT mention any specific project name (e.g., "shopping", "work", "personal")
          2. The user does NOT mention any specific due date or time
        - If the user mentions ANY project name from the available projects list → do NOT set any due date (leave due_date field out entirely) unless the user also explicitly mentions a date/time
        - If the user explicitly mentions a due date/time → always use that date instead of the default
        - For recurring tasks without an explicit due date AND without a project mentioned → set to {default_due_date_value}
        """

    voice_correction_instructions = ""
    if voice_correction:
        voice_correction_instructions = """
        SPEECH RECOGNITION CORRECTION:
        - Task came from voice command - expect speech recognition errors
        - Correct misheard project names, label names, dates, and common speech-to-text errors
        - Ensure the task title is logically consistent with the project name, labels etc. If something doesn't make sense, attempt to find the most likely intended word/phrase based on context
        """

    user_list = []
    if users and isinstance(users, list):
        for u in users:
            if isinstance(u, dict) and u.get("id") is not None:
                user_list.append(
                    {
                        "id": u.get("id"),
                        "name": u.get("name"),
                        "username": u.get("username"),
                    }
                )

    assignment_instructions = ""
    if enable_user_assignment and user_list:
        assignment_instructions = f"""
        USER ASSIGNMENT:
        - You can optionally include an assignee by username or name if clearly specified in the user's description.
        - Output field: assignee (string) MUST be an existing username (preferred) or exact name match from available users.
        - Available users: {json.dumps(user_list)}
        - Only include assignee field if explicitly stated (e.g. 'assign to Alice', 'for william', 'give this to bob').
        - Do not guess if unclear.
        """

    system_message = {
        "role": "system",
        "content": f"""
        You are an assistant that helps create tasks in Vikunja.
        Given a task description, you will create a JSON payload for the Vikunja API.

        Available projects: {json.dumps(project_names)}
        Available labels: {json.dumps(label_names)}

        DEFAULT DUE DATE RULE:
        {default_due_date_instructions.strip() if default_due_date_instructions else "- No default due date configured"}

        {voice_correction_instructions.strip() if voice_correction_instructions else ""}

        CORE OUTPUT REQUIREMENTS:
        - Output ONLY valid JSON with these fields (only include optional fields when applicable):
            * title (string): Main task title (REQUIRED, MUST NOT BE EMPTY)
            * description (string, optional): Only include if the user explicitly asks for additional notes/context.
            * project_id (number): Project ID (always required, use 1 if no project specified)
            * due_date (string, optional): Due date in YYYY-MM-DDTHH:MM:SSZ format
            * priority (number, optional): Priority level 1-5, only when explicitly mentioned
            * repeat_after (number, optional): Repeat interval in seconds, only for recurring tasks
            * label_ids (array, optional): Array of existing label IDs
            * assignee (string, optional): Username (preferred) or exact name of assignee (ONLY if explicitly stated)

        TASK FORMATTING:
        - Extract clear, concise titles.
        - Avoid redundant words implied by project context
        - Remove date/time info from title (use due_date field) if confidently parsed.
        - Remove label references from title (handled via label_ids).
        - Remove project names from title (handled via project_id).
        - Remove priority references from title (handled via priority field).
        - Remove unnecessary qualifiers (e.g. "task", "to do", "reminder")
        - Remove recurring task keywords from title (handled via repeat_after).

        DATE HANDLING (Current: {current_timestamp}):
        - Calculate future dates based on current date: {current_date}
        - Use ISO format with 'Z' timezone: YYYY-MM-DDTHH:MM:SSZ
        - Default time: 12:00:00 (unless specific time mentioned)
        - NEVER set past dates - always use future dates for ambiguous references

        PRIORITY LEVELS (only when explicitly mentioned):
        - 5: urgent, critical, emergency, ASAP, immediately
        - 4: important, soon, priority, needs attention
        - 3: medium priority, when possible, moderately important
        - 2: low priority, when you have time, not urgent
        - 1: sometime, eventually, no rush

        RECURRING TASKS (only when explicitly mentioned):
        - Daily: 86400 seconds | Weekly: 604800 seconds
        - Monthly: 2592000 seconds | Yearly: 31536000 seconds
        - Keywords: daily, weekly, monthly, yearly, every day/week, recurring, repeat...

        EXAMPLES:
        Input: "Reminder to pick up groceries tomorrow"
        Output: {{"title": "Pick up groceries", "project_id": 1, "due_date": "2023-06-09T12:00:00Z"}}

        Input: "URGENT: finish the report for work by Friday at 5pm tagged as urgent"
        Output: {{"title": "Finish work report", "project_id": 1, "due_date": "2023-06-09T17:00:00Z", "priority": 5}}

        Input: "Take vitamins daily with health"
        Output: {{"title": "Take vitamins", "project_id": 1, "repeat_after": 86400}}

        Input: "Add buy milk with the grocery label for next week"
        (Assuming a label with name 'grocery' has id 7)
        Output: {{"title": "Buy milk", "project_id": 1, "label_ids": [7], "due_date": "2023-06-16T12:00:00Z"}}

        Input: "Schedule annual dentist appointment next March"
        Output: {{"title": "Schedule dentist appointment", "project_id": 1, "due_date": "2023-03-01T12:00:00Z"}}

    Input: "Finish the project report"
        (assuming you have default due date settings set up)
        Output: {{"title": "Finish project report", "project_id": 1, "due_date": "2023-06-10T12:00:00Z"}}

    Input: "Buy milk for the shopping project"
        (user mentions a project name → NO default due date)
        Output: {{"title": "Buy milk", "project_id": 5}}

    Input: "Call dentist for work by Friday"
        (user mentions both project AND due date → use the explicit due date)
        Output: {{"title": "Call dentist", "project_id": 2, "due_date": "2023-06-09T12:00:00Z"}}

    Input: "Assign prepare slides to William for next week"
    Output: {{"title": "Prepare slides", "project_id": 1, "due_date": "2023-06-16T12:00:00Z", "assignee": "william"}}

    {assignment_instructions}
        """,
    }

    user_message = {
        "role": "user",
        "content": f"Create task: {task_description}",
    }

    return [system_message, user_message]
