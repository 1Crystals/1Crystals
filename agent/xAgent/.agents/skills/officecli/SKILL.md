---
name: "officecli"
description: "This skill enables interaction with Microsoft Office documents (Word, Excel, PowerPoint) using the OfficeCLI command-line tool on Windows."
---

# OfficeCLI Skill

## Description
This skill enables interaction with Microsoft Office documents (Word, Excel, PowerPoint) using the OfficeCLI command-line tool on Windows.

## Prerequisites
1. Download the Windows version of OfficeCLI and place it in the specified directory.
2. The executable should be accessible via the command line.

## Usage
To use this skill, ensure the OfficeCLI executable (`OfficeCLI-win-x64.exe`) is available in the skill's directory. Common operations include reading, creating, and modifying Office documents.

### Example Commands
- Read a Word document: `OfficeCLI-win-x64.exe read --file document.docx`
- Create an Excel file: `OfficeCLI-win-x64.exe create --file data.xlsx`
- Modify a PowerPoint presentation: `OfficeCLI-win-x64.exe modify --file slides.pptx`

### Reference
For detailed usage, refer to the `OfficeCli操作说明.md` file provided with the tool.

## Notes
- Ensure the OfficeCLI tool is correctly installed and accessible.
- The skill directory should contain the executable and any necessary reference files.
