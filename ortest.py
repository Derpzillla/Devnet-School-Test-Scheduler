"""
Exam Scheduler using Google OR-Tools CP-SAT Solver
This uses constraint programming to find a valid exam schedule
"""

# ============================================================================
# CONFIGURATION - Edit this section to customize paths and settings
# ============================================================================

# Path to the directory containing your RDF data files
DATA_DIRECTORY = r'../data'

# Exam scheduling parameters
# Note: Exam durations are read from classes.ttl (ex:examDuration property)
SLOT_INCREMENT_HOURS = 1      # How often exam slots start (e.g., every hour)
SOLVER_TIME_LIMIT_SECONDS = 300  # Maximum time for solver (5 minutes)

# ============================================================================

from ortools.sat.python import cp_model
from rdflib import Graph, Namespace, RDF, RDFS
from datetime import datetime, timedelta
from collections import defaultdict
import json
import time

# Define common namespaces
EX = Namespace("http://example.org/")
SCHEMA = Namespace("http://schema.org/")


class RDFDataLoader:
    """Loads and parses RDF data from turtle files"""
    
    def __init__(self):
        self.classes = {}           # class_iri -> set of student_iris
        self.students = {}          # student_iri -> set of class_iris
        self.rooms = {}             # room_iri -> capacity (int)
        self.room_availability = {} # room_iri -> list of time slot strings
        self.exam_durations = {}    # class_iri -> duration in hours (float)
        
    def load_from_files(self, classes_file, students_file, rooms_file):
        """Load all RDF data from turtle files"""
        import os
        
        print("Loading RDF data...")
        
        # Helper function to find file in multiple locations
        def find_file(filename):
            possible_paths = [
                os.path.join('..', 'data', filename),  # Up one level, then data folder
                filename,                               # Current directory
                os.path.join('data', filename),        # Data subfolder
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    return path
            
            # If not found, return the first attempted path for error message
            return possible_paths[0]
        
        # Find the actual file paths
        classes_file = find_file(classes_file)
        students_file = find_file(students_file)
        rooms_file = find_file(rooms_file)
        
        # Load graphs
        classes_g = Graph()
        students_g = Graph()
        rooms_g = Graph()
        
        classes_g.parse(classes_file, format='turtle')
        students_g.parse(students_file, format='turtle')
        rooms_g.parse(rooms_file, format='turtle')
        
        print(f"  Loaded from:")
        print(f"    Classes: {classes_file}")
        print(f"    Students: {students_file}")
        print(f"    Rooms: {rooms_file}")
        print(f"  Classes graph: {len(classes_g)} triples")
        print(f"  Students graph: {len(students_g)} triples")
        print(f"  Rooms graph: {len(rooms_g)} triples")
        
        # Parse classes
        self._parse_classes(classes_g)
        
        # Parse students and enrollments
        self._parse_students(students_g)
        
        # Parse rooms
        self._parse_rooms(rooms_g)
        
        print(f"\nParsed data:")
        print(f"  {len(self.classes)} classes")
        print(f"  {len(self.students)} students")
        print(f"  {len(self.rooms)} rooms")
        
        return classes_g, students_g, rooms_g
    
    def _parse_classes(self, graph):
        """Extract class information including exam durations"""
        # Find all subjects that have a type predicate
        # This is flexible to work with various RDF schemas
        for s in graph.subjects(RDF.type, None):
            class_iri = str(s)
            if class_iri not in self.classes:
                self.classes[class_iri] = set()
            
            # Look for exam duration
            for pred, obj in graph.predicate_objects(s):
                pred_str = str(pred).lower()
                
                # Check if this is an exam duration predicate
                if 'examduration' in pred_str or 'exam_duration' in pred_str or 'duration' in pred_str:
                    try:
                        # Try to parse as float (hours)
                        duration = float(str(obj))
                        self.exam_durations[class_iri] = duration
                    except (ValueError, TypeError):
                        # Try to extract number from string
                        import re
                        match = re.search(r'(\d+\.?\d*)', str(obj))
                        if match:
                            self.exam_durations[class_iri] = float(match.group(1))
        
        # Set default duration for classes without one
        default_duration = 3.0  # 3 hours default
        for class_iri in self.classes:
            if class_iri not in self.exam_durations:
                self.exam_durations[class_iri] = default_duration
                print(f"  Warning: No duration found for {class_iri.split('/')[-1]}, using default {default_duration} hours")
    
    def _parse_students(self, graph):
        """Extract student enrollments"""
        # Get all student subjects
        for student_iri in graph.subjects(RDF.type, None):
            student_str = str(student_iri)
            if student_str not in self.students:
                self.students[student_str] = set()
            
            # Look for enrollment predicates
            # Common patterns: enrolledIn, takes, registered, etc.
            for pred, obj in graph.predicate_objects(student_iri):
                pred_str = str(pred).lower()
                
                # Check if this is an enrollment predicate
                if any(keyword in pred_str for keyword in 
                       ['enroll', 'takes', 'registered', 'attends', 'class']):
                    class_iri = str(obj)
                    
                    # Add to student's class list
                    self.students[student_str].add(class_iri)
                    
                    # Add student to class enrollment
                    if class_iri not in self.classes:
                        self.classes[class_iri] = set()
                    self.classes[class_iri].add(student_str)
        
        # Remove students with no enrollments
        self.students = {s: classes for s, classes in self.students.items() if classes}
    
    def _parse_rooms(self, graph):
        """Extract room capacity and availability"""
        for room_iri in graph.subjects(RDF.type, None):
            room_str = str(room_iri)
            capacity = None
            availability_refs = []
            
            for pred, obj in graph.predicate_objects(room_iri):
                pred_str = str(pred).lower()
                obj_str = str(obj)
                
                # Look for capacity
                if 'capacity' in pred_str or 'seats' in pred_str or 'size' in pred_str:
                    try:
                        capacity = int(obj_str)
                    except (ValueError, TypeError):
                        # Try to extract number from string
                        import re
                        match = re.search(r'\d+', obj_str)
                        if match:
                            capacity = int(match.group())
                
                # Look for availability references
                if 'availability' in pred_str or 'hasavailability' in pred_str:
                    availability_refs.append(obj)  # Store the IRI reference, not string
            
            # Now resolve the availability time slots
            availability_slots = []
            for avail_ref in availability_refs:
                # Get availableFrom and availableUntil for this time slot
                available_from = None
                available_until = None
                
                for pred, obj in graph.predicate_objects(avail_ref):
                    pred_str = str(pred).lower()
                    obj_str = str(obj)
                    
                    if 'availablefrom' in pred_str or 'from' in pred_str:
                        available_from = obj_str
                    elif 'availableuntil' in pred_str or 'until' in pred_str or 'to' in pred_str:
                        available_until = obj_str
                
                # Format as a time slot string
                if available_from and available_until:
                    # Remove timezone/datatype suffix if present
                    available_from = available_from.split('^^')[0].strip('"')
                    available_until = available_until.split('^^')[0].strip('"')
                    
                    slot_str = f"{available_from} - {available_until}"
                    availability_slots.append(slot_str)
            
            if capacity:
                self.rooms[room_str] = capacity
                self.room_availability[room_str] = availability_slots if availability_slots else []
                
                # Debug output
                if availability_slots:
                    print(f"  {room_str.split('/')[-1]}: {capacity} seats, {len(availability_slots)} time windows")


class ORToolsScheduler:
    """Constraint Programming scheduler using Google OR-Tools"""
    
    def __init__(self, data_loader):
        self.data = data_loader
        self.model = cp_model.CpModel()
        
        # Will be populated during solve
        self.class_list = []
        self.room_list = []
        self.time_slots = []
        self.time_intervals = []  # Half-hour intervals (for reference)
        
        # Decision variables
        self.class_vars = {}    # (class, room, slot) -> BoolVar
        
        # Solution
        self.schedule = {}
        
        # Solution
        self.schedule = {}
        
    def generate_time_slots(self, slot_increment_hours=1):
        """
        Generate discrete time slots from room availability windows
        Uses actual exam durations from classes data
        
        Args:
            slot_increment_hours: How often to start new slots (e.g., every hour)
        """
        print("\nGenerating time slots based on actual exam durations...")
        
        # Get all unique exam durations
        unique_durations = sorted(set(self.data.exam_durations.values()))
        print(f"  Found {len(unique_durations)} unique exam durations: {unique_durations}")
        
        all_slots_by_duration = defaultdict(set)
        increment = timedelta(hours=slot_increment_hours)
        
        # Generate slots for each duration
        for duration_hours in unique_durations:
            duration = timedelta(hours=duration_hours)
            
            for room_iri, windows in self.data.room_availability.items():
                for window in windows:
                    try:
                        # Parse window: "2026-05-11T08:00:00 - 2026-05-11T18:00:00"
                        parts = window.split(' - ')
                        start = datetime.fromisoformat(parts[0].strip())
                        end = datetime.fromisoformat(parts[1].strip())
                        
                        # Generate slots within this window
                        current = start
                        while current + duration <= end:
                            slot_str = f"{current.isoformat()} - {(current + duration).isoformat()}"
                            all_slots_by_duration[duration_hours].add(slot_str)
                            current += increment
                            
                    except Exception as e:
                        print(f"  Warning: Could not parse time slot '{window}': {e}")
                        continue
        
        # Combine all slots
        all_slots = set()
        for duration, slots in all_slots_by_duration.items():
            print(f"  Generated {len(slots)} slots for {duration}h exams")
            all_slots.update(slots)
        
        # If no slots generated from availability, create default slots
        if not all_slots:
            print("  No slots found in room availability. Creating default slots...")
            # Create 5 days of slots, 8am-6pm, for each unique duration
            base_date = datetime(2026, 5, 11, 8, 0, 0)
            for duration_hours in unique_durations:
                duration = timedelta(hours=duration_hours)
                for day in range(5):
                    for hour in range(0, 10):  # 8am to 6pm
                        current = base_date + timedelta(days=day, hours=hour)
                        slot_str = f"{current.isoformat()} - {(current + duration).isoformat()}"
                        all_slots.add(slot_str)
        
        slots_list = sorted(all_slots)
        print(f"  Total unique time slots: {len(slots_list)}")
        
        return slots_list
    
    def build_model(self, time_slots):
        """
        Build the CP-SAT model with all constraints
        Uses direct interval overlap constraints without intermediate variables
        """
        print("\nBuilding constraint model...")
        
        self.time_slots = time_slots
        self.class_list = sorted(self.data.classes.keys())
        self.room_list = sorted(self.data.rooms.keys())
        
        num_classes = len(self.class_list)
        num_rooms = len(self.room_list)
        num_slots = len(time_slots)
        
        print(f"  Classes: {num_classes}")
        print(f"  Rooms: {num_rooms}")
        print(f"  Time slots: {num_slots}")
        
        # Find global time range from room availability
        print("  Computing time range...")
        all_times = []
        for windows in self.data.room_availability.values():
            for window in windows:
                try:
                    parts = window.split(' - ')
                    start = datetime.fromisoformat(parts[0].strip())
                    end = datetime.fromisoformat(parts[1].strip())
                    all_times.extend([start, end])
                except:
                    pass
        
        if not all_times:
            # Fallback: use slot times
            for slot in time_slots:
                try:
                    parts = slot.split(' - ')
                    start = datetime.fromisoformat(parts[0].strip())
                    end = datetime.fromisoformat(parts[1].strip())
                    all_times.extend([start, end])
                except:
                    pass
        
        global_start = min(all_times)
        global_end = max(all_times)
        
        # Create half-hour intervals
        print("  Creating half-hour time intervals...")
        self.time_intervals = []
        current = global_start
        interval_duration = timedelta(minutes=30)
        
        while current < global_end:
            self.time_intervals.append(current)
            current += interval_duration
        
        num_intervals = len(self.time_intervals)
        print(f"  Total half-hour intervals: {num_intervals}")
        print(f"  Time range: {global_start} to {global_end}")
        
        print(f"  Total decision variables: {num_classes * num_rooms * num_slots}")
        
        # Create decision variables: class_vars[(class, room, slot)] = 1 if scheduled
        print("\n  Creating decision variables...")
        for c_idx, class_iri in enumerate(self.class_list):
            for r_idx, room_iri in enumerate(self.room_list):
                for s_idx, slot in enumerate(time_slots):
                    var_name = f'C{c_idx}_R{r_idx}_S{s_idx}'
                    self.class_vars[(class_iri, room_iri, slot)] = \
                        self.model.NewBoolVar(var_name)
        
        # Pre-compute which slots overlap (for efficiency)
        print("  Pre-computing slot overlap matrix...")
        slot_overlaps = {}  # (slot1_idx, slot2_idx) -> True if they overlap
        for i, slot1 in enumerate(time_slots):
            for j, slot2 in enumerate(time_slots):
                if i != j:
                    slot_overlaps[(i, j)] = self._slots_overlap(slot1, slot2)
        
        print("\n  Adding constraints...")
        
        # CONSTRAINT 1: Each class must be scheduled exactly once
        print("  [1/5] Each class scheduled exactly once")
        for class_iri in self.class_list:
            self.model.Add(
                sum(self.class_vars[(class_iri, room, slot)]
                    for room in self.room_list
                    for slot in time_slots) == 1
            )
        
        # CONSTRAINT 2: Exam duration must match time slot duration
        print("  [2/5] Exam duration matching")
        duration_mismatch_count = 0
        for class_iri in self.class_list:
            exam_duration = self.data.exam_durations.get(class_iri, 3.0)
            
            for slot in time_slots:
                slot_duration = self._get_slot_duration(slot)
                
                if abs(slot_duration - exam_duration) > 0.1:
                    for room_iri in self.room_list:
                        self.model.Add(
                            self.class_vars[(class_iri, room_iri, slot)] == 0
                        )
                    duration_mismatch_count += 1
        
        print(f"      Prevented {duration_mismatch_count} duration mismatches")
        
        # CONSTRAINT 3: Room capacity must not be exceeded
        print("  [3/6] Room capacity")
        for class_iri in self.class_list:
            class_size = len(self.data.classes[class_iri])
            
            for room_iri in self.room_list:
                room_capacity = self.data.rooms[room_iri]
                
                if class_size > room_capacity:
                    for slot in time_slots:
                        self.model.Add(
                            self.class_vars[(class_iri, room_iri, slot)] == 0
                        )
        
        # CONSTRAINT 4: Room availability windows
        print("  [4/6] Room availability (exams must fit in availability windows)")
        availability_violations = 0
        for room_iri in self.room_list:
            available_windows = self.data.room_availability.get(room_iri, [])
            
            if available_windows:  # Only if room has defined availability
                for slot in time_slots:
                    # Check if this slot fits completely within any availability window
                    slot_is_valid = self._slot_within_any_window(slot, available_windows)
                    
                    if not slot_is_valid:
                        # Forbid scheduling any exam in this room at this time
                        for class_iri in self.class_list:
                            self.model.Add(
                                self.class_vars[(class_iri, room_iri, slot)] == 0
                            )
                        availability_violations += 1
        
        print(f"      Prevented {availability_violations} availability violations")
        
        # CONSTRAINT 5: No room double-booking (direct overlap prevention)
        print("  [5/6] Room overlap prevention (prevents double-booking)")
        room_constraints = 0
        for room_iri in self.room_list:
            # For each pair of time slots
            for i, slot1 in enumerate(time_slots):
                for j, slot2 in enumerate(time_slots):
                    if i < j and slot_overlaps.get((i, j), False):
                        # These slots overlap, so can't have two exams in same room
                        for class1 in self.class_list:
                            for class2 in self.class_list:
                                if class1 != class2:
                                    # Can't have class1 at slot1 AND class2 at slot2 in same room
                                    self.model.Add(
                                        self.class_vars[(class1, room_iri, slot1)] +
                                        self.class_vars[(class2, room_iri, slot2)] <= 1
                                    )
                                    room_constraints += 1
        
        print(f"      Added {room_constraints} room overlap constraints")
        
        # CONSTRAINT 6: Student conflict prevention (direct overlap prevention)
        print("  [6/6] Student conflict prevention")
        conflict_constraints = 0
        
        for student_iri, enrolled_classes in self.data.students.items():
            enrolled_list = list(enrolled_classes)
            
            # For each pair of classes this student is enrolled in
            for ci, class1 in enumerate(enrolled_list):
                for cj, class2 in enumerate(enrolled_list):
                    if ci < cj:
                        # For each pair of overlapping time slots
                        for i, slot1 in enumerate(time_slots):
                            for j, slot2 in enumerate(time_slots):
                                if slot_overlaps.get((i, j), False) or slot_overlaps.get((j, i), False) or i == j:
                                    # These slots overlap or are the same
                                    # Student can't be in class1 at slot1 AND class2 at slot2
                                    class1_at_slot1 = sum(
                                        self.class_vars[(class1, room, slot1)]
                                        for room in self.room_list
                                    )
                                    class2_at_slot2 = sum(
                                        self.class_vars[(class2, room, slot2)]
                                        for room in self.room_list
                                    )
                                    
                                    self.model.Add(class1_at_slot1 + class2_at_slot2 <= 1)
                                    conflict_constraints += 1
        
        print(f"      Added {conflict_constraints} student conflict constraints")
        
        # OBJECTIVE: Minimize consecutive exams in different rooms (soft constraint)
        print("\n  Adding objective: Penalize consecutive time slots using different rooms")
        
        penalty_terms = []
        penalty_count = 0
        
        # For each pair of consecutive time slots
        for i, slot1 in enumerate(time_slots):
            for j, slot2 in enumerate(time_slots):
                # Check if slot2 starts when slot1 ends (back-to-back)
                if self._slots_are_consecutive(slot1, slot2):
                    # For each pair of different rooms
                    for room1 in self.room_list:
                        for room2 in self.room_list:
                            if room1 != room2:  # Only penalize different rooms
                                # Add penalty term for: 
                                # (any exam in room1 at slot1) AND (any exam in room2 at slot2)
                                
                                # Sum of exams in room1 at slot1
                                room1_at_slot1 = sum(
                                    self.class_vars[(cls, room1, slot1)] 
                                    for cls in self.class_list
                                )
                                
                                # Sum of exams in room2 at slot2  
                                room2_at_slot2 = sum(
                                    self.class_vars[(cls, room2, slot2)]
                                    for cls in self.class_list
                                )
                                
                                # Create indicator: 1 if both rooms are used consecutively
                                both_used = self.model.NewBoolVar(f'penalty_{penalty_count}')
                                
                                # both_used = 1 IFF both room1_at_slot1 AND room2_at_slot2 are >= 1
                                self.model.Add(both_used * 2 <= room1_at_slot1 + room2_at_slot2)
                                self.model.Add(both_used >= room1_at_slot1 + room2_at_slot2 - 1)
                                
                                penalty_terms.append(both_used)
                                penalty_count += 1
        
        if penalty_terms:
            # Minimize the sum of penalties
            self.model.Minimize(sum(penalty_terms))
            print(f"      Added {penalty_count} room transition penalties")
            print(f"      (Each penalty = consecutive exams in different rooms)")
        else:
            print(f"      No consecutive slots found for penalty")
        
        print("\n✓ Model built successfully")
    
    def _get_intervals_for_slot(self, slot):
        """
        Get list of half-hour interval indices that this slot occupies
        """
        try:
            parts = slot.split(' - ')
            start = datetime.fromisoformat(parts[0].strip())
            end = datetime.fromisoformat(parts[1].strip())
            
            intervals = []
            interval_duration = timedelta(minutes=30)
            
            # Find all intervals that overlap with this slot
            for idx, interval_start in enumerate(self.time_intervals):
                interval_end = interval_start + interval_duration
                
                # Check if this interval overlaps with the slot
                # Intervals overlap if: interval_start < slot_end AND interval_end > slot_start
                if interval_start < end and interval_end > start:
                    intervals.append(idx)
            
            return intervals
        except Exception as e:
            print(f"    Warning: Could not parse slot '{slot}': {e}")
            return []
    
    def _slots_overlap(self, slot1, slot2):
        """Check if two time slots overlap"""
        try:
            # Parse slot1
            parts1 = slot1.split(' - ')
            start1 = datetime.fromisoformat(parts1[0].strip())
            end1 = datetime.fromisoformat(parts1[1].strip())
            
            # Parse slot2  
            parts2 = slot2.split(' - ')
            start2 = datetime.fromisoformat(parts2[0].strip())
            end2 = datetime.fromisoformat(parts2[1].strip())
            
            # Check for overlap: not (one ends before other starts)
            return not (end1 <= start2 or end2 <= start1)
        except Exception:
            # If parsing fails, assume they don't overlap (permissive)
            return False
    
    def _slots_are_consecutive(self, slot1, slot2):
        """Check if slot2 starts immediately when slot1 ends (back-to-back)"""
        try:
            parts1 = slot1.split(' - ')
            end1 = datetime.fromisoformat(parts1[1].strip())
            
            parts2 = slot2.split(' - ')
            start2 = datetime.fromisoformat(parts2[0].strip())
            
            # Consecutive if end of slot1 equals start of slot2
            return end1 == start2
        except Exception:
            return False
    
    def _get_slot_duration(self, slot):
        """Get the duration of a time slot in hours"""
        try:
            parts = slot.split(' - ')
            start = datetime.fromisoformat(parts[0].strip())
            end = datetime.fromisoformat(parts[1].strip())
            duration = (end - start).total_seconds() / 3600.0  # Convert to hours
            return duration
        except Exception:
            return 3.0  # Default to 3 hours if parsing fails
    
    def _slot_within_any_window(self, slot, windows):
        """Check if a time slot fits within any availability window"""
        try:
            slot_parts = slot.split(' - ')
            slot_start = datetime.fromisoformat(slot_parts[0].strip())
            slot_end = datetime.fromisoformat(slot_parts[1].strip())
            
            for window in windows:
                window_parts = window.split(' - ')
                window_start = datetime.fromisoformat(window_parts[0].strip())
                window_end = datetime.fromisoformat(window_parts[1].strip())
                
                # Check if slot is completely within window
                if window_start <= slot_start and slot_end <= window_end:
                    return True
            
            return False
            
        except Exception:
            # If parsing fails, allow the slot (permissive)
            return True
    
    def solve(self, time_limit_seconds=300):
        """
        Solve the constraint model
        
        Args:
            time_limit_seconds: Maximum time to spend solving (default 5 minutes)
        """
        print(f"\nSolving (time limit: {time_limit_seconds}s)...")
        
        # Create solver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        solver.parameters.log_search_progress = True
        
        # Solve
        start_time = time.time()
        status = solver.Solve(self.model)
        elapsed = time.time() - start_time
        
        print(f"\nSolver finished in {elapsed:.2f} seconds")
        print(f"Status: {solver.StatusName(status)}")
        
        if status == cp_model.OPTIMAL:
            print("✓ Found OPTIMAL solution")
            self._extract_solution(solver)
            return True
        elif status == cp_model.FEASIBLE:
            print("✓ Found FEASIBLE solution (may not be optimal)")
            self._extract_solution(solver)
            return True
        elif status == cp_model.INFEASIBLE:
            print("✗ Problem is INFEASIBLE - no solution exists")
            self._diagnose_infeasibility()
            return False
        else:
            print(f"✗ Solver status: {solver.StatusName(status)}")
            return False
    
    def _extract_solution(self, solver):
        """Extract the schedule from the solved model"""
        print("\nExtracting solution...")
        
        for class_iri in self.class_list:
            for room_iri in self.room_list:
                for slot in self.time_slots:
                    # Check if this variable is set to 1
                    if solver.Value(self.class_vars[(class_iri, room_iri, slot)]) == 1:
                        # Found the assignment for this class
                        self.schedule[class_iri] = {
                            'room': room_iri,
                            'time_slot': slot,
                            'students': list(self.data.classes[class_iri])
                        }
                        break
        
        print(f"✓ Extracted {len(self.schedule)} exam schedules")
    
    def _diagnose_infeasibility(self):
        """Provide diagnostic information when problem is infeasible"""
        print("\nDiagnosing infeasibility...")
        
        # Check if there are enough room-slot combinations
        total_capacity = sum(self.data.rooms.values()) * len(self.time_slots)
        total_students = sum(len(students) for students in self.data.classes.values())
        
        print(f"  Total room capacity across all slots: {total_capacity}")
        print(f"  Total student-exam assignments needed: {total_students}")
        
        # Check for very large classes
        print("\n  Checking for capacity issues...")
        max_capacity = max(self.data.rooms.values())
        for class_iri, students in self.data.classes.items():
            if len(students) > max_capacity:
                print(f"    ⚠ Class {class_iri.split('/')[-1]} has {len(students)} students")
                print(f"      but largest room only holds {max_capacity}")
        
        # Check for heavy student loads
        print("\n  Checking student course loads...")
        max_load = max(len(classes) for classes in self.data.students.values())
        print(f"    Maximum courses per student: {max_load}")
        print(f"    Available time slots: {len(self.time_slots)}")
        
        if max_load > len(self.time_slots):
            print(f"    ⚠ Some students need {max_load} slots but only {len(self.time_slots)} available")
    
    def to_json(self):
        """
        Convert schedule to required JSON format
        
        Format:
        {
          "group_0001": {
            "students": ["http://example.org/_StudentA", ...],
            "room": {
              "room_iri": "http://example.org/RoomA",
              "start": "2026-05-11T08:00:00",
              "end": "2026-05-11T11:00:00"
            },
            "class_iri": "http://example.org/MATH101"
          }
        }
        """
        output = {}
        
        for i, (class_iri, assignment) in enumerate(self.schedule.items(), 1):
            group_id = f"group_{i:04d}"
            
            # Parse the time slot to extract start and end times
            time_slot = assignment['time_slot']
            start_time, end_time = self._parse_time_slot_for_json(time_slot)
            
            output[group_id] = {
                "students": assignment['students'],
                "room": {
                    "room_iri": assignment['room'],
                    "start": start_time,
                    "end": end_time
                },
                "class_iri": class_iri
            }
        
        return output
    
    def _parse_time_slot_for_json(self, time_slot):
        """
        Parse time slot string and return start and end as separate strings
        Input: "2026-05-11T08:00:00 - 2026-05-11T11:00:00"
        Output: ("2026-05-11T08:00:00", "2026-05-11T11:00:00")
        """
        parts = time_slot.split(' - ')
        start = parts[0].strip()
        end = parts[1].strip()
        return start, end
    
    def print_summary(self):
        """Print a summary of the schedule"""
        print("\n" + "="*60)
        print("SCHEDULE SUMMARY")
        print("="*60)
        
        print(f"\nTotal exams scheduled: {len(self.schedule)}")
        print(f"Total students: {len(self.data.students)}")
        
        # Room utilization
        room_usage = defaultdict(int)
        for assignment in self.schedule.values():
            room_usage[assignment['room']] += 1
        
        print(f"\nRoom utilization:")
        for room, count in sorted(room_usage.items(), key=lambda x: x[1], reverse=True):
            print(f"  {room.split('/')[-1]}: {count} exams")
        
        # Time slot utilization
        slot_usage = defaultdict(int)
        for assignment in self.schedule.values():
            slot_usage[assignment['time_slot']] += 1
        
        print(f"\nTime slot utilization (top 10):")
        for slot, count in sorted(slot_usage.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {slot}: {count} exams")
        
        # Student schedule verification
        print(f"\nVerifying student schedules...")
        conflicts = 0
        for student, classes in self.data.students.items():
            student_slots = []
            for class_iri in classes:
                if class_iri in self.schedule:
                    student_slots.append(self.schedule[class_iri]['time_slot'])
            
            # Check for duplicates (conflicts)
            if len(student_slots) != len(set(student_slots)):
                conflicts += 1
        
        if conflicts == 0:
            print("  ✓ No student conflicts detected")
        else:
            print(f"  ⚠ Found {conflicts} students with conflicting exam times")


def main():
    """Main execution function"""
    print("="*60)
    print("EXAM SCHEDULER - Google OR-Tools Implementation")
    print("="*60)
    
    # Use configured data directory
    import os
    data_dir = DATA_DIRECTORY
    
    print(f"\nConfiguration:")
    print(f"  Data directory: {data_dir}")
    print(f"  Slot increment: {SLOT_INCREMENT_HOURS} hours")
    print(f"  Solver time limit: {SOLVER_TIME_LIMIT_SECONDS} seconds")
    print(f"  Note: Exam durations will be read from classes.ttl")
    
    # Load data (paths will be auto-resolved)
    loader = RDFDataLoader()
    
    try:
        # Try configured directory first, then auto-resolve
        if os.path.exists(data_dir):
            classes_file = os.path.join(data_dir, 'classes.ttl')
            students_file = os.path.join(data_dir, 'students.ttl')
            rooms_file = os.path.join(data_dir, 'rooms.ttl')
        else:
            # Auto-resolve will find them in ../data/ or current dir
            classes_file = 'classes.ttl'
            students_file = 'students.ttl'
            rooms_file = 'rooms.ttl'
        
        loader.load_from_files(classes_file, students_file, rooms_file)
    except FileNotFoundError as e:
        print(f"\n✗ Error: {e}")
        print(f"\nPlease ensure the following files exist in:")
        print(f"  {data_dir}")
        print("\nRequired files:")
        print("  - classes.ttl")
        print("  - students.ttl")
        print("  - rooms.ttl")
        return
    except Exception as e:
        print(f"\n✗ Error loading RDF data: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Validate data
    if not loader.classes:
        print("\n✗ No classes found in RDF data")
        return
    if not loader.students:
        print("\n✗ No students found in RDF data")
        return
    if not loader.rooms:
        print("\n✗ No rooms found in RDF data")
        return
    
    # Create scheduler
    scheduler = ORToolsScheduler(loader)
    
    # Generate time slots
    time_slots = scheduler.generate_time_slots(
        slot_increment_hours=SLOT_INCREMENT_HOURS
    )
    
    if not time_slots:
        print("\n✗ No time slots generated")
        return
    
    # Build constraint model
    scheduler.build_model(time_slots)
    
    # Solve
    success = scheduler.solve(time_limit_seconds=SOLVER_TIME_LIMIT_SECONDS)
    
    if success:
        # Print summary
        scheduler.print_summary()
        
        # Save to JSON in the data directory
        print("\nSaving schedule to file...")
        output = scheduler.to_json()
        
        output_file = os.path.join('Ben_F_Submission', 'exam_schedule.json')
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
            #json.dump('exam_schedule.json', f, indent=2)
        
        print(f"✓ Schedule saved to {output_file}")
        
    else:
        print("\n✗ Failed to find a valid schedule")
        print("Please review the diagnostic information above")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()