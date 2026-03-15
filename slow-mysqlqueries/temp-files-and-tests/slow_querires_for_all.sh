#!/bin/bash

RED_COLOR=$'\033[31;1m'
GREEN_COLOR=$'\e[40;38;5;82m'
DEFAULT_COLOR=$'\033[0m'

# Function to convert timeframe to hours
convert_timeframe_to_hours() {
    case $time_unit in
        hour | hours)
            time_in_hours=$time_num
            ;;
        day | days)
            time_in_hours=$(( time_num * 24 ))
            ;;
        week | weeks)
            time_in_hours=$(( time_num * 168 ))
            ;;
        *)
            echo "Incorrect Timeframe. Try Again"
            ;;
    esac
}

# Function to generate slow query log for a specific user
generate_slow_query_log_for_user() {
    cp_user="$1"
    slow_query_log_for_user="/home/$cp_user/slow-queries-$(date +'%d-%b-%Y').txt"

    # Generate slow query log for the specific user
    if [ "$timeframe" != 'none' ]; then
        tail -n +"$line_num" "$slow_query_log" | awk -v user="$cp_user" '{ if ($0 ~ user ) { start = 1; print; } else if ($0 ~ /# User@Host:/) { start = 0 } else if (start) { print } }' > "$slow_query_log_for_user"
    else
        < "$slow_query_log" awk -v user="$cp_user" '{ if ($0 ~ user ) { start = 1; print; } else if ($0 ~ /# User@Host:/) {start = 0 } else if (start) { print } }' > "$slow_query_log_for_user"
    fi

    # Add additional information to the log file
    if [ -s "$slow_query_log_for_user" ]; then
        line_num_to_add=$(tail -n +"$line_num" "$slow_query_log" | grep -nm1 "$cp_user" | cut -d ':' -f 1)
        ((line_num_to_add--))
        line_value_to_add=$(tail -n +"$line_num" "$slow_query_log" | sed -n "$line_num_to_add"p)

        sed -i "1s/^/$line_value_to_add\n/" "$slow_query_log_for_user"
        sed -i '$d' "$slow_query_log_for_user"

        chown "$cp_user": "$slow_query_log_for_user"
        echo "${RED_COLOR}Slow query log for user $cp_user generated: $slow_query_log_for_user${DEFAULT_COLOR}"
    else
        rm -f "$slow_query_log_for_user"  # Remove the empty file
        echo "${GREEN_COLOR}No slow queries found for user $cp_user${DEFAULT_COLOR}"
    fi
}

# Prompt for cPanel user or "all"
read -e -r -p $'\e[94mEnter cPanel User (or "all" for all users):\e[0m ' cp_user_input
cp_user_input=$(echo "$cp_user_input" | awk '{print tolower($0)}')

# Fetch valid cPanel users
valid_cpanel_users=$(whmapi1 listaccts | grep 'user:' | awk '{print $2}')

# Debug: Print out the list of valid users for verification
echo "Valid cPanel users detected: $valid_cpanel_users"

# Determine if "all" or specific user is selected
if [ "$cp_user_input" == "all" ]; then
    # Use valid_cpanel_users to loop over all cPanel accounts
    cpanel_users="$valid_cpanel_users"
else
    # Check if the provided user exists in the valid users list
    if echo "$valid_cpanel_users" | grep -qw "$cp_user_input"; then
        cpanel_users="$cp_user_input"
    else
        echo "${RED_COLOR}Invalid cPanel user: $cp_user_input${DEFAULT_COLOR}"
        exit 1
    fi
fi

# Prompt for timeframe
read -e -r -p $'\e[36mTimeframe (e.g., 3 hours, 1 day, 5 weeks, etc. or "none" to review all entries in the logs):\e[0m ' timeframe

# Process timeframe input
if [ "$timeframe" != 'none' ]; then
    time_num=$(echo "$timeframe" | tr -dc '0-9')
    time_unit=$(echo "$timeframe" | tr -dc 'a-zA-Z' | awk '{print tolower($0)}')
    convert_timeframe_to_hours

    # Set slow query log path
    slow_query_log=$(grep slow_query_log_file /etc/my.cnf | awk '{print$3}')

    # Find line number in slow query log
    num_of_hours="$time_in_hours"
    while [ "$num_of_hours" -ge 0 ]; do
        line_num=$(grep -nam 1 "$(date -d -"$num_of_hours"hours +'%Y-%m-%dT%H')" "$slow_query_log" | cut -d ':' -f1)
        if [ ! -z "$line_num" ]; then
            break
        fi
        ((num_of_hours--))
        if [ "$num_of_hours" -lt 0 ]; then
            printf "%sNo entries found for the specified timeframe.%s\\n" "$GREEN_COLOR" "$DEFAULT_COLOR"
            break
        fi
    done
fi

# Loop through each cPanel user
for cp_user in $cpanel_users; do
    # Generate slow query log for the user
    generate_slow_query_log_for_user "$cp_user"
done

