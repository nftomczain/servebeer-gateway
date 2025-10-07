#!/bin/bash
echo "Top 10 requested CIDs today:"
sqlite3 database/servebeer.db "SELECT details, COUNT(*) FROM audit_log WHERE date(timestamp) = date('now') GROUP BY details ORDER BY COUNT(*) DESC LIMIT 10"
