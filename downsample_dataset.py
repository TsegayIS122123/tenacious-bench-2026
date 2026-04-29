#!/usr/bin/env python3
"""
Downsample Tenacious-Bench from 503 to exactly 250 tasks
Maintains 50/30/20 partition split and source mode ratios
"""

import json
import random
import shutil
from pathlib import Path
from collections import Counter

SEED = 421
random.seed(SEED)

TARGET_TOTAL = 250
TRAIN_TARGET = 125   # 50%
DEV_TARGET = 75      # 30%
HELD_OUT_TARGET = 50 # 20%

SOURCE_MODE_TARGETS = {
    "trace-derived": 0.30,      # 75 tasks
    "programmatic": 0.30,       # 75 tasks
    "multi-llm-synthesis": 0.25, # 62 tasks
    "hand-adversarial": 0.15    # 38 tasks
}

def load_tasks_by_mode(partition_dir):
    """Load all tasks and group by source_mode"""
    tasks_by_mode = {mode: [] for mode in SOURCE_MODE_TARGETS.keys()}
    
    for task_file in partition_dir.glob("*.json"):
        if ".metadata" in str(task_file):
            continue
        try:
            with open(task_file, 'r') as f:
                task = json.load(f)
                mode = task.get("source_mode", "unknown")
                if mode in tasks_by_mode:
                    tasks_by_mode[mode].append((task_file, task))
        except Exception as e:
            print(f"  Warning: Could not load {task_file}: {e}")
    
    return tasks_by_mode

def select_tasks_by_mode(tasks_by_mode, target_count):
    """Select tasks preserving source mode ratios"""
    selected_files = []
    
    for mode, target_ratio in SOURCE_MODE_TARGETS.items():
        mode_target = int(target_count * target_ratio)
        available = len(tasks_by_mode[mode])
        to_select = min(mode_target, available)
        
        if to_select > 0:
            selected = random.sample(tasks_by_mode[mode], to_select)
            selected_files.extend([f for f, _ in selected])
            print(f"    {mode}: {to_select}/{available} selected")
    
    # If we need more due to rounding, add from any mode
    if len(selected_files) < target_count:
        all_remaining = []
        for mode, tasks in tasks_by_mode.items():
            for task_file, _ in tasks:
                if task_file not in selected_files:
                    all_remaining.append(task_file)
        needed = target_count - len(selected_files)
        extra = random.sample(all_remaining, min(needed, len(all_remaining)))
        selected_files.extend(extra)
    
    return selected_files

def verify_partition(partition_dir, expected_count):
    """Verify partition has correct number of tasks"""
    actual = len(list(partition_dir.glob("*.json")))
    # Exclude metadata files
    actual = len([f for f in partition_dir.glob("*.json") if ".metadata" not in str(f)])
    return actual

def main():
    base = Path("tenacious_bench_v0.1")
    
    # Create backup
    backup_dir = Path("tenacious_bench_v0.1_backup_503")
    if not backup_dir.exists():
        print("í³¦ Creating backup of original 503-task dataset...")
        shutil.copytree(base, backup_dir)
        print(f"   Backup saved to: {backup_dir}")
    
    print(f"\ní¾¯ Downsampling from 503 to {TARGET_TOTAL} tasks")
    print(f"   Train target: {TRAIN_TARGET}")
    print(f"   Dev target: {DEV_TARGET}")
    print(f"   Held-out target: {HELD_OUT_TARGET}")
    
    # Process each partition
    for partition_name, target_count in [("train", TRAIN_TARGET), ("dev", DEV_TARGET), ("held_out", HELD_OUT_TARGET)]:
        partition_dir = base / partition_name
        print(f"\ní³Š Processing {partition_name} (target: {target_count})...")
        
        # Load tasks by mode
        tasks_by_mode = load_tasks_by_mode(partition_dir)
        
        # Select tasks
        selected_files = select_tasks_by_mode(tasks_by_mode, target_count)
        
        # Delete unselected files
        for task_file in partition_dir.glob("*.json"):
            if ".metadata" in str(task_file):
                continue
            if task_file not in selected_files:
                task_file.unlink()
                # Also delete corresponding metadata file
                metadata_file = partition_dir / f"{task_file.stem}.metadata.json"
                if metadata_file.exists():
                    metadata_file.unlink()
        
        # Verify
        final_count = verify_partition(partition_dir, target_count)
        print(f"   âœ… {partition_name}: {final_count} tasks (target: {target_count})")
    
    # Final verification
    print("\n" + "="*50)
    print("FINAL VERIFICATION")
    print("="*50)
    
    train_count = verify_partition(base / "train", TRAIN_TARGET)
    dev_count = verify_partition(base / "dev", DEV_TARGET)
    held_count = verify_partition(base / "held_out", HELD_OUT_TARGET)
    total = train_count + dev_count + held_count
    
    print(f"   Train: {train_count} (target: {TRAIN_TARGET})")
    print(f"   Dev: {dev_count} (target: {DEV_TARGET})")
    print(f"   Held-out: {held_count} (target: {HELD_OUT_TARGET})")
    print(f"   TOTAL: {total} (target: {TARGET_TOTAL})")
    
    if total == TARGET_TOTAL:
        print("\nâœ… SUCCESS: Dataset is now exactly 250 tasks")
    else:
        print(f"\nâš ï¸ WARNING: Total is {total}, expected {TARGET_TOTAL}")
    
    print(f"\ní³ Backup of original 503-task dataset: {backup_dir}")
    print("   To restore: rm -rf tenacious_bench_v0.1 && mv tenacious_bench_v0.1_backup_503 tenacious_bench_v0.1")

if __name__ == "__main__":
    main()
