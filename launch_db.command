#!/bin/bash
# Get absolute path of the project
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Path to your SQLite database
DB_PATH="$PROJECT_DIR/articles.db"

# Open a new Terminal window and start sqlite3 on articles.db
osascript <<EOF
tell application "Terminal"
    do script "cd '$PROJECT_DIR'; sqlite3 '$DB_PATH'"
    activate
end tell
EOF
