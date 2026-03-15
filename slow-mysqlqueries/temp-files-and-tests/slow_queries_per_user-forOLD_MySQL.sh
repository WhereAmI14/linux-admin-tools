#/bin/bash

read -e -r -p $'\e[36mcPanel User:\e[0m ' cp_user;

while (true); do

read -e -r -p $'\e[36mTimeframe(3 hours, 1 day, 5 weeks, ect. or none to review all entries in the logs):\e[0m ' timeframe;

 if [ "$timeframe" != 'none' ]; then

  time_num=$( echo $timeframe | tr -dc '0-9' )
  time_unit=$( echo $timeframe | tr -dc 'a-zA-Z' )

  case $time_unit in

   hour | hours)
    timevar=$time_num
    break 2
    ;;

   day | days)
    timevar=$(( time_num * 24 ))
    break 2
    ;;

   week | weeks)
    timevar=$(( time_num * 168 ))
    break 2
    ;;

  *)
    echo "incorrect timeframe. Try Again"
    ;;

  esac

 else

  break

 fi

done

if [ "$timeframe" != 'none' ]; then

 hours=$timevar
 while [ "$hours" -ge 0 ]; do

  line_num=$(grep -nam 1 "$(date -d -"$hours"hours +'%Y-%m-%dT%H')" /var/lib/mysql/mysql-slow.log  | cut -d ':' -f1)

  if [ ! -z "$line_num" ]; then

   break

  fi

   ((hours--));

  if [ "$hours" -lt 0 ]; then

    #PRINT NO ENTRIES FOUND IN THE PROVIDED TIMEFRAME
   exit

  fi
 done
fi

cp_user_length=${#cp_user}

if [ "$cp_user_length" -ge 8 ]; then

  db_user=$( echo "$cp_user" | cut -c 1-8 )

else

 db_user=$( echo "$cp_user" )

fi

log_file_name="/home/"$cp_user"/slow-queries-$(date +'%d-%b-%Y').txt"

if [ "$timeframe" != 'none' ]; then

 tail -n +"$line_num" /var/lib/mysql/mysql-slow.log | awk -v user="$db_user" '{ if ($0 ~ user ) { start = 1; print; } else if ($0 ~ /# User@Host:/) { start = 0 } else if (start) { print } }' > "$log_file_name"

else

 cat /var/lib/mysql/mysql-slow.log | awk -v user="$db_user" '{ if ($0 ~ user ) { start = 1; print; } else if ($0 ~ /# User@Host:/) { start = 0 } else if (start) { print } }' > "$log_file_name"

fi

if [ -s "$log_file_name" ]; then

 chown "$cp_user": "$log_file_name"
 echo LOG FILE GENERATED: "$log_file_name"

 read -e -r -p $'\e[36mWold you like to review the number of queries in the report and the time needed for the 10 slowest queries to be executed ?(y/n)\e[0m ' review;

 if [ "$review" = y ]; then

  echo Total Number of Queries:
  cat "$log_file_name" | grep 'Query_time' | wc -l

  echo Execution time of the 10 slowest queries in the logs:
  cat "$log_file_name" | grep 'Query_time' | cut -d ' ' -f 3 | sort -rh | head

 fi
fi
