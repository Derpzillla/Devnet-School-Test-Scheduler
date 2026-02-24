"""
Exam Schedule Visualization
Creates a timeline chart showing room usage over time with exam occupancy counts
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap, BoundaryNorm
from datetime import datetime, timedelta
import numpy as np
from collections import defaultdict
import sys, os

filepath2 = os.path.join('Ben_F_Submission', 'exam_schedule.json')
def load_schedule(filepath2):
    """Load the exam schedule JSON"""
    try:
        with open(filepath2, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find {filepath2}")
        sys.exit(1)


def parse_datetime(dt_string):
    """Parse ISO format datetime string"""
    return datetime.fromisoformat(dt_string)


def get_unique_classes(schedule):
    """Get all unique class IRIs and assign them colors"""
    classes = set()
    for group_data in schedule.values():
        classes.add(group_data['class_iri'])
    return sorted(classes)


def assign_colors(classes):
    """Assign a unique color to each class"""
    # Use a colormap with many distinct colors
    n_classes = len(classes)
    
    if n_classes <= 10:
        colors = plt.cm.tab10(np.linspace(0, 1, 10))[:n_classes]
    elif n_classes <= 20:
        colors = plt.cm.tab20(np.linspace(0, 1, 20))[:n_classes]
    else:
        # For many classes, use a perceptually uniform colormap
        colors = plt.cm.viridis(np.linspace(0, 1, n_classes))
    
    color_map = {}
    for i, class_iri in enumerate(classes):
        color_map[class_iri] = colors[i]
    
    return color_map


def create_room_timeline_chart(schedule, output_file='exam_schedule_timeline.png'):
    """
    Create a Gantt-chart style visualization with rooms on Y-axis and time on X-axis
    Each exam is shown as a colored rectangle with occupancy count
    """
    print("Creating room timeline visualization...")
    
    # Extract data
    rooms = {}
    classes = get_unique_classes(schedule)
    color_map = assign_colors(classes)
    
    # Organize data by room
    for group_id, group_data in schedule.items():
        room_iri = group_data['room']['room_iri']
        start_time = parse_datetime(group_data['room']['start'])
        end_time = parse_datetime(group_data['room']['end'])
        class_iri = group_data['class_iri']
        num_students = len(group_data['students'])
        
        if room_iri not in rooms:
            rooms[room_iri] = []
        
        rooms[room_iri].append({
            'start': start_time,
            'end': end_time,
            'class': class_iri,
            'students': num_students,
            'group_id': group_id
        })
    
    # Sort rooms by name for consistent display
    room_list = sorted(rooms.keys())
    
    # Find time range
    all_times = []
    for exams in rooms.values():
        for exam in exams:
            all_times.append(exam['start'])
            all_times.append(exam['end'])
    
    min_time = min(all_times)
    max_time = max(all_times)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(16, max(8, len(room_list) * 0.6)))
    
    # Plot each room's exams
    for i, room_iri in enumerate(room_list):
        room_name = room_iri.split('/')[-1]  # Get just the room name
        exams = rooms[room_iri]
        
        # Sort exams by start time
        exams.sort(key=lambda x: x['start'])
        
        for exam in exams:
            start = exam['start']
            end = exam['end']
            duration = (end - start).total_seconds() / 3600  # Hours
            
            # Calculate position
            start_hours = (start - min_time).total_seconds() / 3600
            
            # Get color for this class
            color = color_map[exam['class']]
            
            # Draw rectangle for exam
            rect = mpatches.Rectangle(
                (start_hours, i - 0.4),  # (x, y)
                duration,  # width
                0.8,  # height
                facecolor=color,
                edgecolor='black',
                linewidth=1,
                alpha=0.8
            )
            ax.add_patch(rect)
            
            # Add text showing number of students
            text_x = start_hours + duration / 2
            text_y = i
            
            # Format the label
            class_name = exam['class'].split('/')[-1]
            
            # Adjust label based on exam duration
            if duration >= 3:
                label = f"{class_name}\n{exam['students']} students"
                fontsize = 8
            elif duration >= 1.5:
                label = f"{class_name}\n{exam['students']}"
                fontsize = 8
            else:
                label = f"{exam['students']}"
                fontsize = 7
            
            # Add text with white background for readability
            ax.text(text_x, text_y, label,
                   ha='center', va='center',
                   fontsize=fontsize, fontweight='bold',
                   color='white',
                   bbox=dict(boxstyle='round,pad=0.4', 
                            facecolor='black', 
                            edgecolor='none',
                            alpha=0.7),
                   zorder=10)
    
    # Set up axes
    ax.set_yticks(range(len(room_list)))
    ax.set_yticklabels([r.split('/')[-1] for r in room_list])
    ax.set_ylabel('Room', fontsize=12, fontweight='bold')
    
    # X-axis formatting with hourly ticks
    total_hours = (max_time - min_time).total_seconds() / 3600
    ax.set_xlim(0, total_hours)
    ax.set_xlabel('Time', fontsize=12, fontweight='bold')
    
    # Create hourly time labels
    hour_positions = []
    hour_labels = []
    
    current_hour = 0
    while current_hour <= total_hours:
        hour_positions.append(current_hour)
        time_point = min_time + timedelta(hours=current_hour)
        hour_labels.append(time_point.strftime('%b %d\n%H:%M'))
        current_hour += 1
    
    ax.set_xticks(hour_positions)
    ax.set_xticklabels(hour_labels, rotation=45, ha='right', fontsize=8)
    
    # Grid
    ax.grid(True, axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    # Title
    title = f'Exam Schedule Timeline - Room Occupancy\n'
    title += f'{len(schedule)} exams across {len(room_list)} rooms'
    ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
    
    # Add legend for classes (show up to 15 classes in legend)
    if len(classes) <= 15:
        legend_elements = []
        for class_iri in classes:
            class_name = class_iri.split('/')[-1]
            legend_elements.append(
                mpatches.Patch(facecolor=color_map[class_iri], 
                             edgecolor='black',
                             label=class_name)
            )
        
        ax.legend(handles=legend_elements, 
                 loc='center left', 
                 bbox_to_anchor=(1, 0.5),
                 fontsize=8,
                 title='Classes',
                 title_fontsize=10)
    else:
        # Too many classes for legend
        ax.text(1.02, 0.5, f'{len(classes)} different classes\n(too many to list)', 
               transform=ax.transAxes, 
               fontsize=10,
               va='center')
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved timeline chart to {output_file}")
    plt.close()


def create_occupancy_heatmap(schedule, output_file='exam_schedule_heatmap.png'):
    """
    Create a heatmap showing room occupancy levels over time
    """
    print("\nCreating occupancy heatmap...")
    
    # Get all rooms and time slots
    rooms = {}
    all_start_times = set()
    
    for group_data in schedule.values():
        room_iri = group_data['room']['room_iri']
        start_time = parse_datetime(group_data['room']['start'])
        end_time = parse_datetime(group_data['room']['end'])
        num_students = len(group_data['students'])
        
        if room_iri not in rooms:
            rooms[room_iri] = []
        
        rooms[room_iri].append({
            'start': start_time,
            'end': end_time,
            'students': num_students
        })
        
        all_start_times.add(start_time)
    
    # Sort rooms and times
    room_list = sorted(rooms.keys())
    time_slots = sorted(all_start_times)
    
    # Create occupancy matrix
    occupancy_matrix = np.zeros((len(room_list), len(time_slots)))
    
    for i, room_iri in enumerate(room_list):
        for j, time_slot in enumerate(time_slots):
            # Check if this room has an exam at this time
            for exam in rooms[room_iri]:
                if exam['start'] == time_slot:
                    occupancy_matrix[i, j] = exam['students']
                    break
    
    # Create heatmap
    fig, ax = plt.subplots(figsize=(16, max(8, len(room_list) * 0.4)))
    
    # Use a colormap
    im = ax.imshow(occupancy_matrix, cmap='YlOrRd', aspect='auto')
    
    # Set ticks
    ax.set_yticks(range(len(room_list)))
    ax.set_yticklabels([r.split('/')[-1] for r in room_list])
    
    ax.set_xticks(range(len(time_slots)))
    time_labels = [t.strftime('%b %d\n%H:%M') for t in time_slots]
    ax.set_xticklabels(time_labels, rotation=45, ha='right', fontsize=8)
    
    # Labels
    ax.set_ylabel('Room', fontsize=12, fontweight='bold')
    ax.set_xlabel('Exam Start Time', fontsize=12, fontweight='bold')
    ax.set_title('Room Occupancy Heatmap\n(Number of Students per Exam)', 
                fontsize=14, fontweight='bold', pad=20)
    
    # Colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Number of Students', rotation=270, labelpad=20, fontsize=10)
    
    # Add text annotations for occupancy counts
    for i in range(len(room_list)):
        for j in range(len(time_slots)):
            count = int(occupancy_matrix[i, j])
            if count > 0:
                text_color = 'white' if count > occupancy_matrix.max() * 0.6 else 'black'
                ax.text(j, i, str(count), ha='center', va='center',
                       color=text_color, fontsize=8, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved heatmap to {output_file}")
    plt.close()


def create_utilization_summary(schedule, output_file='exam_schedule_summary.png'):
    """
    Create summary statistics visualization
    """
    print("\nCreating utilization summary...")
    
    # Collect statistics
    room_usage = defaultdict(int)
    time_slot_usage = defaultdict(int)
    class_counts = defaultdict(int)
    occupancy_counts = []
    
    for group_data in schedule.values():
        room_iri = group_data['room']['room_iri']
        start_time = parse_datetime(group_data['room']['start'])
        class_iri = group_data['class_iri']
        num_students = len(group_data['students'])
        
        room_usage[room_iri] += 1
        time_slot_usage[start_time] += 1
        class_counts[class_iri] += 1
        occupancy_counts.append(num_students)
    
    # Create figure with subplots
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. Room utilization bar chart
    ax1 = axes[0, 0]
    rooms = [r.split('/')[-1] for r in sorted(room_usage.keys())]
    counts = [room_usage[r] for r in sorted(room_usage.keys())]
    
    bars = ax1.barh(rooms, counts, color='steelblue', edgecolor='black')
    ax1.set_xlabel('Number of Exams', fontsize=10, fontweight='bold')
    ax1.set_ylabel('Room', fontsize=10, fontweight='bold')
    ax1.set_title('Room Utilization', fontsize=12, fontweight='bold')
    ax1.grid(axis='x', alpha=0.3)
    
    # Add value labels on bars
    for bar in bars:
        width = bar.get_width()
        ax1.text(width, bar.get_y() + bar.get_height()/2, 
                f'{int(width)}', 
                ha='left', va='center', fontsize=8, fontweight='bold')
    
    # 2. Time slot utilization
    ax2 = axes[0, 1]
    times = sorted(time_slot_usage.keys())
    time_labels = [t.strftime('%b %d %H:%M') for t in times]
    slot_counts = [time_slot_usage[t] for t in times]
    
    ax2.bar(range(len(times)), slot_counts, color='coral', edgecolor='black')
    ax2.set_xticks(range(len(times)))
    ax2.set_xticklabels(time_labels, rotation=90, ha='right', fontsize=7)
    ax2.set_ylabel('Number of Exams', fontsize=10, fontweight='bold')
    ax2.set_xlabel('Time Slot', fontsize=10, fontweight='bold')
    ax2.set_title('Time Slot Usage', fontsize=12, fontweight='bold')
    ax2.grid(axis='y', alpha=0.3)
    
    # 3. Occupancy distribution
    ax3 = axes[1, 0]
    ax3.hist(occupancy_counts, bins=20, color='seagreen', edgecolor='black', alpha=0.7)
    ax3.set_xlabel('Number of Students', fontsize=10, fontweight='bold')
    ax3.set_ylabel('Number of Exams', fontsize=10, fontweight='bold')
    ax3.set_title('Exam Size Distribution', fontsize=12, fontweight='bold')
    ax3.grid(axis='y', alpha=0.3)
    
    # Add statistics text
    stats_text = f'Mean: {np.mean(occupancy_counts):.1f}\n'
    stats_text += f'Median: {np.median(occupancy_counts):.1f}\n'
    stats_text += f'Min: {min(occupancy_counts)}\n'
    stats_text += f'Max: {max(occupancy_counts)}'
    ax3.text(0.95, 0.95, stats_text,
            transform=ax3.transAxes,
            fontsize=9,
            verticalalignment='top',
            horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    # 4. Summary statistics table
    ax4 = axes[1, 1]
    ax4.axis('off')
    
    summary_stats = [
        ['Metric', 'Value'],
        ['Total Exams', f'{len(schedule)}'],
        ['Total Rooms Used', f'{len(room_usage)}'],
        ['Total Time Slots Used', f'{len(time_slot_usage)}'],
        ['Total Classes', f'{len(class_counts)}'],
        ['Average Exams per Room', f'{len(schedule) / len(room_usage):.2f}'],
        ['Average Occupancy', f'{np.mean(occupancy_counts):.1f} students'],
        ['Total Student-Exams', f'{sum(occupancy_counts)}'],
    ]
    
    table = ax4.table(cellText=summary_stats,
                     cellLoc='left',
                     loc='center',
                     colWidths=[0.6, 0.4])
    
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)
    
    # Style the header row
    for i in range(2):
        table[(0, i)].set_facecolor('#4CAF50')
        table[(0, i)].set_text_props(weight='bold', color='white')
    
    # Alternate row colors
    for i in range(1, len(summary_stats)):
        for j in range(2):
            if i % 2 == 0:
                table[(i, j)].set_facecolor('#f0f0f0')
    
    ax4.set_title('Summary Statistics', fontsize=12, fontweight='bold', pad=20)
    
    plt.suptitle('Exam Schedule Analysis', fontsize=16, fontweight='bold', y=0.995)
    plt.tight_layout(rect=[0, 0, 1, 0.99])
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved summary to {output_file}")
    plt.close()


def create_daily_overview(schedule, output_file='exam_schedule_daily.png'):
    """
    Create a daily overview showing exam distribution across days
    """
    print("\nCreating daily overview...")
    
    # Group by day
    daily_exams = defaultdict(list)
    
    for group_data in schedule.values():
        start_time = parse_datetime(group_data['room']['start'])
        day = start_time.date()
        
        daily_exams[day].append({
            'time': start_time.time(),
            'class': group_data['class_iri'].split('/')[-1],
            'room': group_data['room']['room_iri'].split('/')[-1],
            'students': len(group_data['students'])
        })
    
    # Sort days
    days = sorted(daily_exams.keys())
    
    # Create figure
    n_days = len(days)
    fig, axes = plt.subplots(1, n_days, figsize=(5*n_days, 8))
    
    if n_days == 1:
        axes = [axes]
    
    for i, day in enumerate(days):
        ax = axes[i]
        exams = daily_exams[day]
        
        # Sort by time
        exams.sort(key=lambda x: x['time'])
        
        # Create timeline
        y_pos = np.arange(len(exams))
        colors = plt.cm.Set3(np.linspace(0, 1, len(exams)))
        
        bars = ax.barh(y_pos, [e['students'] for e in exams], color=colors, edgecolor='black')
        
        # Labels
        labels = [f"{e['time'].strftime('%H:%M')} - {e['class']}\n{e['room']}" for e in exams]
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel('Number of Students', fontsize=10, fontweight='bold')
        ax.set_title(day.strftime('%A\n%B %d, %Y'), fontsize=12, fontweight='bold')
        ax.grid(axis='x', alpha=0.3)
        
        # Add value labels
        for bar, exam in zip(bars, exams):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2,
                   f' {exam["students"]}',
                   ha='left', va='center', fontsize=8, fontweight='bold')
    
    plt.suptitle('Daily Exam Overview', fontsize=16, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Saved daily overview to {output_file}")
    plt.close()


def main():
    """Main visualization function"""
    import sys
    
    print("="*70)
    print("EXAM SCHEDULE VISUALIZATION")
    print("="*70 + "\n")
    
    # Get schedule file path
    if len(sys.argv) > 1:
        schedule_file = sys.argv[1]
    else:
        schedule_file = 'exam_schedule.json'
    
    print(f"Loading schedule from: {schedule_file}\n")
    
    # Load schedule
    schedule = load_schedule(schedule_file)
    print(f"Loaded {len(schedule)} exam groups\n")
    
    # Create visualizations
    print("Generating visualizations...")
    print("-" * 70)
    
    create_room_timeline_chart(schedule)
    create_occupancy_heatmap(schedule)
    create_utilization_summary(schedule)
    create_daily_overview(schedule)
    
    print("\n" + "="*70)
    print("VISUALIZATION COMPLETE")
    print("="*70)
    print("\nGenerated files:")
    print("  1. exam_schedule_timeline.png  - Room timeline with occupancy")
    print("  2. exam_schedule_heatmap.png   - Occupancy heatmap")
    print("  3. exam_schedule_summary.png   - Summary statistics")
    print("  4. exam_schedule_daily.png     - Daily overview")
    print("\n" + "="*70)


if __name__ == "__main__":
    main()