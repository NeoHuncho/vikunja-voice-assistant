import logging
import json
import aiohttp
from datetime import datetime, timezone, timedelta
import socket
import asyncio

_LOGGER = logging.getLogger(__name__)

async def process_with_openai(task_description, projects, api_key, model, default_due_date="none", voice_correction=False):
    """Process the task with OpenAI API directly."""
    project_names = [{"id": p.get("id"), "name": p.get("title")} for p in projects]
    
    # Get current date and time in ISO format to provide context
    current_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Calculate default due dates
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=12, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_of_week = (datetime.now(timezone.utc) + timedelta(days=7)).replace(hour=17, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_of_month = (datetime.now(timezone.utc) + timedelta(days=30)).replace(hour=17, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Default due date instructions based on config
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
        - If no specific project or due date is mentioned in the task, use this default due date: {default_due_date_value}
        - If a specific project is mentioned, do not set any due date unless the user explicitly mentions one
        - If a specific due date is mentioned by the user, always use that instead of the default
        - Even if a recurring task instruction is given, if no due date is mentioned, set it to {default_due_date_value}
        """
    
    # Add voice correction instructions if enabled
    voice_correction_instructions = ""
    if voice_correction:
        voice_correction_instructions = """
        SPEECH RECOGNITION CORRECTION:
        - Task came from voice command - expect speech recognition errors
        - Correct misheard project names, dates, and common speech-to-text errors
        - Use context to understand user's true intent
        """
    
    system_message = {
        "role": "system",
        "content": f"""
        You are an assistant that helps create tasks in Vikunja. 
        Given a task description, you will create a JSON payload for the Vikunja API.
        
        Available projects: {json.dumps(project_names)}
        
        DEFAULT DUE DATE RULE:
        {default_due_date_instructions.strip() if default_due_date_instructions else "- No default due date configured"}
        
        {voice_correction_instructions.strip() if voice_correction_instructions else ""}
        
        CORE OUTPUT REQUIREMENTS:
        - Output only valid JSON with these fields (only include optional fields when applicable):
          * title (string): Main task title (REQUIRED, MUST NOT BE EMPTY)
          * description (string): Task details (always include, use empty string if none)
          * project_id (number): Project ID (always required, use 1 if no project specified)
          * due_date (string, optional): Due date in YYYY-MM-DDTHH:MM:SSZ format
          * priority (number, optional): Priority level 1-5, only when explicitly mentioned
          * repeat_after (number, optional): Repeat interval in seconds, only for recurring tasks
        
        TASK FORMATTING:
        - Extract clear, concise titles from task descriptions
        - Avoid redundant words already implied by project context
        - Remove date/time information from titles (put in due_date field instead)
        - Include relevant details in description field
        
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
        - Keywords: daily, weekly, monthly, yearly, every day/week, recurring, repeat
        
        EXAMPLES:
        Input: "Reminder to pick up groceries tomorrow"
        Output: {{"title": "Pick up groceries", "description": "", "project_id": 1, "due_date": "2023-06-09T12:00:00Z"}}
        
        Input: "URGENT: I need to finish the report for work by Friday at 5pm"
        Output: {{"title": "Finish work report", "description": "Complete and submit the report", "project_id": 1, "due_date": "2023-06-09T17:00:00Z", "priority": 5}}
        
        Input: "Take vitamins daily"
        Output: {{"title": "Take vitamins", "description": "", "project_id": 1, "repeat_after": 86400}}
        
        Input: "Weekly team meeting every Monday at 10am"
        Output: {{"title": "Team meeting", "description": "", "project_id": 1, "due_date": "2023-06-12T10:00:00Z", "repeat_after": 604800}}
        
        Input: "Call the dentist next Tuesday" (misheard as "dentiest")
        Output: {{"title": "Call the dentist", "description": "", "project_id": 1, "due_date": "2023-06-13T12:00:00Z"}}
        
        Input: "Buy milk for the grocery project tomorrow at 3" (unclear time)
        Output: {{"title": "Buy milk", "description": "", "project_id": 2, "due_date": "2023-06-09T15:00:00Z"}}
        
        Input: "Schedule meeting with client for next Friday" (no specific time)
        Output: {{"title": "Schedule meeting with client", "description": "", "project_id": 1, "due_date": "2023-06-16T12:00:00Z"}}
        """
    }
    
    user_message = {
        "role": "user",
        "content": f"Create a task with this description (be sure to include a title): {task_description}"
    }
    payload = {
        "model": model,
        "messages": [system_message, user_message],
        "temperature": 0.7
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Define timeouts to prevent hanging
    timeout = aiohttp.ClientTimeout(total=60, connect=15, sock_read=30, sock_connect=15)  # Increased timeouts
    _LOGGER.info(f"Attempting to connect to OpenAI API to process task: '{task_description[:50]}...'")
    
    try:
        # Skip explicit DNS resolution which might be causing timeout issues
        async with aiohttp.ClientSession(timeout=timeout) as session:
            _LOGGER.debug("Sending request to OpenAI API")
            try:
                openai_url = "https://api.openai.com/v1/chat/completions"
                
                async with session.post(
                    openai_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                    ssl=False  # Try disabling SSL verification temporarily to troubleshoot
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error(f"OpenAI API error: {response.status} - {error_text}")
                        return None
                    
                    result = await response.json()
                    _LOGGER.debug("Successfully received response from OpenAI API")
                    
                    # Extract the JSON from the response
                    raw_response = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    try:
                        # Find JSON in the response if it's wrapped in other text
                        start_idx = raw_response.find('{')
                        end_idx = raw_response.rfind('}') + 1
                        if start_idx >= 0 and end_idx > start_idx:
                            json_str = raw_response[start_idx:end_idx]
                            # Validate the JSON
                            task_data = json.loads(json_str)
                            
                            # Ensure required fields are present
                            if "title" not in task_data or not task_data["title"]:
                                _LOGGER.error("OpenAI response missing required 'title' field")
                                _LOGGER.debug("Raw OpenAI response: %s", raw_response)
                                return None
                                
                            _LOGGER.info(f"Successfully processed task: '{task_data.get('title', 'Unknown')}'")
                            return json_str
                        else:
                            _LOGGER.error("No JSON found in OpenAI response")
                            _LOGGER.debug("Raw OpenAI response: %s", raw_response)
                            return None
                    except (json.JSONDecodeError, ValueError) as err:
                        _LOGGER.error("Failed to parse JSON from OpenAI response: %s", err)
                        _LOGGER.debug("Raw OpenAI response: %s", raw_response)
                        return None
            
            except asyncio.TimeoutError as timeout_err:
                _LOGGER.error(f"Timeout while connecting to OpenAI API: {timeout_err}")
                return None
            except aiohttp.ClientConnectorError as conn_err:
                _LOGGER.error(f"Connection error to OpenAI API: {conn_err}")
                return None
                
    except aiohttp.ClientError as client_err:
        _LOGGER.error(f"HTTP client error with OpenAI: {client_err}")
        return None
    except asyncio.TimeoutError as timeout_err:
        _LOGGER.error(f"Timeout error with OpenAI: {timeout_err}")
        return None
    except Exception as err:
        _LOGGER.error(f"Error processing with OpenAI: {err}", exc_info=True)
        return None