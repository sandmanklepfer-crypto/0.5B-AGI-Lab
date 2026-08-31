#!/usr/bin/env python3
"""SELinux policy 深度审计: shell 域全部权限分类扫描"""
import sys
from setools import SELinuxPolicy, TERuleQuery

p = SELinuxPolicy('/workspace/policy.bin')

def scan(source, title, classes=None, min_perms=None):
    print(f"\n{'='*60}\n{title} (source={source})\n{'='*60}")
    seen = {}
    for r in TERuleQuery(p, source=source).results():
        try:
            perms = sorted(r.perms)
        except Exception:
            continue  # type_transition 等无权限集规则
        tgt = str(r.target)
        tcl = str(r.tclass)
        if classes and tcl not in classes:
            continue
        key = (tgt, tcl)
        if key not in seen:
            seen[key] = set()
        seen[key].update(perms)
    for (tgt, tcl), perms in sorted(seen.items()):
        if min_perms and not min_perms.issubset(perms):
            continue
        print(f"  {tgt:40s} {tcl:12s} [{','.join(sorted(perms))}]")
    print(f"  -- 共 {len(seen)} 条")

# 1. capability (内核能力: sys_admin/net_admin 等大权限)
scan("shell", "=== capability (内核特权能力) ===", classes=["capability","capability2"])

# 2. process (ptrace/kill/exec 其他进程)
scan("shell", "=== process (进程操作) ===", classes=["process"], min_perms={"ptrace"})

# 3. property (Android 属性系统)
scan("shell", "=== property (可写系统属性) ===", classes=["property_service"])

# 4. binder (binder 调用/引用)
scan("shell", "=== binder (可调用/引用) ===", classes=["binder"])

# 5. 文件系统写权限 (dir/file 带 write)
scan("shell", "=== file/dir 可写 (写权限) ===", classes=["file","dir"], min_perms={"write"})

# 6. sysfs/proc 写
scan("shell", "=== sysfs/proc 相关写 ===", classes=["file"], min_perms={"write"})
