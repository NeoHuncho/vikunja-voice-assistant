<div align="center">

# 🎙️ Vikunja Voice Assistant for Home Assistant

<img src="https://raw.githubusercontent.com/NeoHuncho/vikunja-voice-assistant/main/logo.png" alt="Vikunja Voice Assistant logo" width="160" />

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)[![HACS Default](https://img.shields.io/badge/HACS-Default-blue.svg)](https://hacs.xyz/)

Say **“create a task”** or **“add a task”** → Your task goes straight into Vikunja!

*[Video Demo 🎥](https://github.com/user-attachments/assets/c592b0e8-efc6-40d1-ad53-a442de69bfc5)*
</div>


> **⚠️ Important Notice (Breaking Changes):**
> This version now uses Home Assistant's AI Task (`ai_task.generate_data`) pipeline instead of calling OpenAI directly.
> After updating from a version before 2.0.0, you MUST reconfigure the integration and **select a compatible AI Task entity**.


---

## ✨ Features

* **Natural voice commands**: *"Create a task…"* or *"Add a task…"* 🗣️
* Supports **project, due date, priority, labels, recurrence** and more 📅
* Optional: speech correction, auto voice label, default due date, user assignment
* Supports 11 languages 🌐 [📖 Voice commands in all 11 languages](VOICE_COMMANDS.md)

---

## 📦 Requirements

* [Home Assistant](https://www.home-assistant.io/) with a [voice assistant set up](https://www.home-assistant.io/voice_control/)
* [HACS](https://hacs.xyz/docs/use/download/download/#to-download-hacs-ossupervised)
* Running Vikunja instance + API token with [correct permissions](https://github.com/NeoHuncho/vikunja-voice-assistant?tab=readme-ov-file#%EF%B8%8F-installation-hacs--full-video-walkthrough)
* Configured Home Assistant AI Task entity (from the `ai_task.generate_data` pipeline)

---

## ⚙️ Installation (HACS) | [Video Guide](https://github.com/user-attachments/assets/c897b523-2539-42e2-ba03-fa9534a80c36)

⏱️ *Create your first task in under 2 minutes!*

1. In HACS → Search: **Vikunja Voice Assistant** → Install

2. Restart Home Assistant

3. Go to *Settings → Devices & Services → Add Integration*

4. Search: **Vikunja Voice Assistant**

5. Fill out setup form (Vikunja URL, API token, AI Task entity, options)

   * **Vikunja API Token** → User Settings → API Tokens

     * **Set the following permissions**:
     * Labels: Create and Read All
     * Projects: Read All, Projectusers (optional - for user assignment)
     * Tasks: Create

       📹 [Video Guide](https://github.com/user-attachments/assets/f131c6bb-2e78-4feb-b72e-7c76ec3fbaf2)       

   * **AI Task entity** [Video Guide OpenRouter](https://github.com/user-attachments/assets/2202b199-a30e-4fb2-8e55-1f998dffe9ea)

     Select the Home Assistant `ai_task` entity that is configured to run your preferred LLM via `ai_task.generate_data`.

     Note: this integration relies on Home Assistant's AI Task pipeline (`ai_task.generate_data`). You can use any AI provider compatible with AI Task (examples: Ollama, OpenAI, Google Gemini, OpenRouter). See AI & LLM setup and the AI Task integration for details:

     - AI & LLM setup: [LINK](https://www.home-assistant.io/integrations/?cat=ai)
     - AI Task (`ai_task`) integration: [LINK](https://www.home-assistant.io/integrations/ai_task/)

6. ✅ Done – Just say **"create a task"** !

---

## 🔧 Configuration Options

| Option                           | Purpose                                                      | Example/Default |
| -------------------------------- | ------------------------------------------------------------ | --------------- |
| Speech correction                | Fix common speech-to-text errors                             | Enabled         |
| Auto `voice` label               | Attaches/creates a `voice` label                             | Enabled         |
| Default due date                 | Used if no date & no project given                           | tomorrow        |
| Default due date choices         | none, tomorrow, end\_of\_week, end\_of\_month                | tomorrow        |
| Enable user assignment           | Assign tasks to existing users                               | Disabled        |
| Detailed response                | Speak back project, labels, due date, assignee, priority & repeat info | On             |

---

## 🤖 AI Conversation Agent (Recommended)

Append this to your Home Assistant Voice Assistant’s conversation Agent custom instructions:


```
If the user mentions or implies creating or adding a new task,
always call this tool (do not leave any field empty):

tool_name: VikunjaAddTask
tool_args: {
  task_description: "<exact user sentence>",
}
```
*This will allow your voice assistant to create tasks even if the keywords were missing.*




📹 [Video Guide](https://github.com/user-attachments/assets/0440bc71-b748-4118-8afd-6f0f10b22003)

---
## 🗺️ Roadmap
Check the [roadmap project](https://github.com/users/NeoHuncho/projects/1) to see and add your feature requests! ✍️

---

## 🚧 Limitations

* ❌ Cannot create new labels (except auto-creating **voice**)
* ❌ Cannot create new projects
* ❌ Cannot create new assignee users (only assign existing)
* ❌ Only works with one language at a time (selected Home Assistant language)

---

## 📜 License

MIT – see [LICENSE](LICENSE).
