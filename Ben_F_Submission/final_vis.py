"""
Daily Stacked Exam Schedule Visualization
Each day gets its own timeline row for better readability
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime, timedelta
import numpy as np
import sys


def load_schedule(filepath):
    """Load the exam schedule JSON"""
    with open(filepath, 'r') as f:
        return json.load(f)


def load_room_availability():
    """Load room availability from rooms.ttl"""
    from rdflib import Graph, RDF
    import os
    
    print("Loading room availability from rooms.ttl...")
    
    # Try multiple possible paths
    possible_paths = [
        '../data/rooms.ttl',  # Up one level, then data folder
        'rooms.ttl',          # Current directory
        'data/rooms.ttl',     # Data subfolder
    ]
    
    rooms_g = Graph()
    loaded = False
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                rooms_g.parse(path, format='turtle')
                print(f"  Loaded from: {path}")
                loaded = True
                break
            except Exception as e:
                print(f"  Failed to parse {path}: {e}")
                continue
    
    if not loaded:
        print(f"  Warning: Could not find rooms.ttl in any of these locations:")
        for path in possible_paths:
            print(f"    - {path}")
        print("  Continuing without availability display...\n")
        return {}
    
    try:
        room_availability = {}
        
        for room_iri in rooms_g.subjects(RDF.type, None):
            room_str = str(room_iri)
            availability_refs = []
            
            # Get availability references
            for pred, obj in rooms_g.predicate_objects(room_iri):
                pred_str = str(pred).lower()
                if 'availability' in pred_str or 'hasavailability' in pred_str:
                    availability_refs.append(obj)
            
            # Resolve availability time slots
            availability_slots = []
            for avail_ref in availability_refs:
                available_from = None
                available_until = None
                
                for pred, obj in rooms_g.predicate_objects(avail_ref):
                    pred_str = str(pred).lower()
                    obj_str = str(obj)
                    
                    if 'availablefrom' in pred_str or 'from' in pred_str:
                        available_from = obj_str
                    elif 'availableuntil' in pred_str or 'until' in pred_str or 'to' in pred_str:
                        available_until = obj_str
                
                if available_from and available_until:
                    # Remove datatype suffix
                    available_from = available_from.split('^^')[0].strip('"')
                    available_until = available_until.split('^^')[0].strip('"')
                    
                    slot_str = f"{available_from} - {available_until}"
                    availability_slots.append(slot_str)
            
            if availability_slots:
                room_availability[room_str] = availability_slots
        
        print(f"  Loaded availability for {len(room_availability)} rooms\n")
        return room_availability
        
    except Exception as e:
        print(f"  Warning: Error processing room availability: {e}")
        print("  Continuing without availability display...\n")
        return {}


def visualize_schedule_by_day(schedule_file='exam_schedule.json', output_file='schedule_by_day.png'):
    """
    Create visualization with each day as a separate row
    Within each day row, show all rooms
    Grey blocks show unscheduled room availability
    """
    
    print(f"Loading schedule from {schedule_file}...")
    schedule = load_schedule(schedule_file)
    print(f"Loaded {len(schedule)} exams\n")
    
    # Load room availability
    room_availability = load_room_availability()
    
    # Extract data and organize by day
    rooms = {}
    all_classes = set()
    exams_by_day = {}
    
    for group_id, data in schedule.items():
        room_iri = data['room']['room_iri']
        class_iri = data['class_iri']
        start = datetime.fromisoformat(data['room']['start'])
        end = datetime.fromisoformat(data['room']['end'])
        num_students = len(data['students'])
        
        all_classes.add(class_iri)
        
        # Group by day
        day = start.date()
        if day not in exams_by_day:
            exams_by_day[day] = {}
        
        if room_iri not in exams_by_day[day]:
            exams_by_day[day][room_iri] = []
        
        exams_by_day[day][room_iri].append({
            'start': start,
            'end': end,
            'class': class_iri,
            'students': num_students
        })
    
    # Assign colors to classes
    classes_list = sorted(all_classes)
    if len(classes_list) <= 10:
        colors = plt.cm.tab10(np.linspace(0, 1, 10))
    elif len(classes_list) <= 20:
        colors = plt.cm.tab20(np.linspace(0, 1, 20))
    else:
        colors = plt.cm.gist_rainbow(np.linspace(0, 1, len(classes_list)))
    
    class_colors = {cls: colors[i] for i, cls in enumerate(classes_list)}
    
    # Get all rooms
    all_rooms = set()
    for day_exams in exams_by_day.values():
        all_rooms.update(day_exams.keys())
    room_list = sorted(all_rooms)
    
    # Sort days
    days = sorted(exams_by_day.keys())
    
    print(f"Days: {len(days)}")
    print(f"Rooms: {len(room_list)}")
    print(f"Classes: {len(classes_list)}\n")
    
    # Create figure with subplots (one per day)
    n_days = len(days)
    fig_height = max(3, n_days * 3)  # 3 inches per day
    fig, axes = plt.subplots(n_days, 1, figsize=(18, fig_height))
    
    # Handle single day case
    if n_days == 1:
        axes = [axes]
    
    # Plot each day
    for day_idx, day in enumerate(days):
        ax = axes[day_idx]
        day_exams = exams_by_day[day]
        
        # Find time range for this day
        day_start = datetime.combine(day, datetime.min.time())
        day_end = datetime.combine(day, datetime.max.time())
        
        # Get actual min/max times for this day
        all_times = []
        for room_exams in day_exams.values():
            for exam in room_exams:
                all_times.extend([exam['start'], exam['end']])
        
        if all_times:
            min_time = min(all_times)
            max_time = max(all_times)
            
            # Round to nearest hour for cleaner display
            min_hour = min_time.replace(minute=0, second=0, microsecond=0)
            max_hour = (max_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        else:
            min_hour = day_start + timedelta(hours=8)
            max_hour = day_start + timedelta(hours=20)
        
        total_hours = (max_hour - min_hour).total_seconds() / 3600
        
        # First, draw grey blocks for ALL room availability on this day
        print(f"  Drawing availability for {day.strftime('%A, %b %d')}...")
        for room_idx, room_iri in enumerate(room_list):
            # Get this room's availability windows
            room_avail = room_availability.get(room_iri, [])
            
            for window in room_avail:
                try:
                    # Parse availability window
                    parts = window.split(' - ')
                    avail_start = datetime.fromisoformat(parts[0].strip())
                    avail_end = datetime.fromisoformat(parts[1].strip())
                    
                    # Check if this window is on the current day
                    if avail_start.date() == day:
                        # Calculate position relative to day start
                        window_start_hours = (avail_start - min_hour).total_seconds() / 3600
                        window_duration = (avail_end - avail_start).total_seconds() / 3600
                        
                        # Draw grey background for available time
                        grey_rect = mpatches.Rectangle(
                            (window_start_hours, room_idx - 0.45),
                            window_duration,
                            0.9,
                            facecolor='#E0E0E0',  # Light grey
                            edgecolor='#AAAAAA',
                            linewidth=1,
                            alpha=0.5,
                            zorder=1  # Behind everything
                        )
                        ax.add_patch(grey_rect)
                except:
                    continue
        
        # Then, plot scheduled exams on top
        for room_idx, room_iri in enumerate(room_list):
            room_exams = day_exams.get(room_iri, [])
            
            for exam in room_exams:
                # Calculate positions relative to day start
                start_hours = (exam['start'] - min_hour).total_seconds() / 3600
                duration_hours = (exam['end'] - exam['start']).total_seconds() / 3600
                
                # Get color
                color = class_colors[exam['class']]
                
                # Draw rectangle
                rect = mpatches.Rectangle(
                    (start_hours, room_idx - 0.4),
                    duration_hours,
                    0.8,
                    facecolor=color,
                    edgecolor='black',
                    linewidth=1.5,
                    alpha=0.85,
                    zorder=5  # On top of grey
                )
                ax.add_patch(rect)
                
                # Add text label
                text_x = start_hours + duration_hours / 2
                text_y = room_idx
                
                class_short = exam['class'].split('/')[-1]
                
                # Format label based on duration
                if duration_hours >= 3:
                    label = f"{class_short}\n{exam['students']}"
                    fontsize = 9
                elif duration_hours >= 1.5:
                    label = f"{class_short}\n{exam['students']}"
                    fontsize = 8
                else:
                    label = f"{exam['students']}"
                    fontsize = 7
                
                ax.text(text_x, text_y, label,
                       ha='center', va='center',
                       fontsize=fontsize,
                       fontweight='bold',
                       color='white',
                       bbox=dict(boxstyle='round,pad=0.4',
                               facecolor='black',
                               edgecolor='none',
                               alpha=0.7),
                       zorder=10)  # Text on top
        
        # Y-axis (Rooms)
        ax.set_ylim(-0.5, len(room_list) - 0.5)
        ax.set_yticks(range(len(room_list)))
        room_labels = [r.split('/')[-1] for r in room_list]
        ax.set_yticklabels(room_labels, fontsize=10)
        ax.set_ylabel('Room', fontsize=11, fontweight='bold')
        
        # X-axis (Time) - hourly ticks
        ax.set_xlim(0, total_hours)
        
        hour_positions = []
        hour_labels = []
        
        current_hour = 0
        while current_hour <= total_hours:
            hour_positions.append(current_hour)
            time_point = min_hour + timedelta(hours=current_hour)
            hour_labels.append(time_point.strftime('%H:%M'))
            current_hour += 1
        
        ax.set_xticks(hour_positions)
        ax.set_xticklabels(hour_labels, rotation=45, ha='right', fontsize=9)
        ax.set_xlabel('Time', fontsize=11, fontweight='bold')
        
        # Grid
        ax.grid(True, axis='x', alpha=0.3, linestyle='--', linewidth=0.5)
        ax.set_axisbelow(True)
        
        # Title for each day
        day_name = day.strftime('%A, %B %d, %Y')
        n_exams_today = sum(len(exams) for exams in day_exams.values())
        ax.set_title(f'{day_name} - {n_exams_today} exams', 
                    fontsize=12, fontweight='bold', pad=10)
    
    # Overall title
    fig.suptitle(f'Exam Schedule by Day - {len(schedule)} exams across {len(room_list)} rooms',
                fontsize=14, fontweight='bold', y=0.995)
    
    # Add legend at the bottom
    if len(classes_list) <= 20:
        # Create legend elements
        legend_elements = []
        
        # Add grey block for availability
        legend_elements.append(
            mpatches.Patch(
                facecolor='#E0E0E0',
                edgecolor='#AAAAAA',
                label='Available (unscheduled)',
                alpha=0.5
            )
        )
        
        # Add colored blocks for classes
        for class_iri in classes_list:
            class_name = class_iri.split('/')[-1]
            legend_elements.append(
                mpatches.Patch(
                    facecolor=class_colors[class_iri],
                    edgecolor='black',
                    label=class_name
                )
            )
        
        # Add legend below the plots
        fig.legend(
            handles=legend_elements,
            loc='lower center',
            bbox_to_anchor=(0.5, -0.02),
            ncol=min(10, len(classes_list)),
            fontsize=9,
            title='Exam Types',
            title_fontsize=10,
            frameon=True
        )
        
        plt.subplots_adjust(bottom=0.05 + (len(classes_list) // 10) * 0.03)
    else:
        textstr = f'{len(classes_list)} different exam types'
        fig.text(0.5, 0.02, textstr, ha='center', fontsize=10,
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout(rect=[0, 0.05, 1, 0.99])
    
    print(f"Saving visualization to {output_file}...")
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Visualization saved!\n")
    
    plt.close()
    
    # Print summary
    print("="*70)
    print("SUMMARY BY DAY")
    print("="*70)
    
    for day in days:
        day_name = day.strftime('%A, %B %d')
        n_exams = sum(len(exams) for exams in exams_by_day[day].values())
        print(f"{day_name}: {n_exams} exams")
    
    print("="*70)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        schedule_file = sys.argv[1]
    else:
        schedule_file = 'exam_schedule.json'
    
    try:
        visualize_schedule_by_day(schedule_file)
    except FileNotFoundError:
        print(f"Error: Could not find {schedule_file}")
        print("Usage: python visualize_schedule_by_day.py [path/to/exam_schedule.json]")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)