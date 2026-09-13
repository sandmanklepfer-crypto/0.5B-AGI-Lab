R=/root/autodl-tmp/_ARM.txt
rm -f $R
echo "===== armor_v4c.py 全文 =====" >> $R
cat /root/armor_v4c.py >> $R 2>&1
echo "" >> $R
echo "===== 其他对齐脚本 =====" >> $R
ls -la /root/*armor* /root/*align* /root/*safety* /root/*refuse* 2>/dev/null >> $R
echo "ARM_DONE" >> $R
