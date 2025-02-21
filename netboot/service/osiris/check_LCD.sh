################
modetest | grep preferred > /tmp/lcd.log
lcd=$(cut -c 3-12 /tmp/lcd.log | head -1)

if [ $lcd == "2256x1504" ];
  then
   ectool cbi set 2 0x120021 4
elif [ $lcd == "1290x1080" ];
  then
   ectool cbi set 2 0x120020 4
fi
