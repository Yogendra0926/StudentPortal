import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import pymysql
import pymysql.cursors
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
# Give the study materials its own unique config key
app.config['STUDY_MATERIALS_FOLDER'] = 'static/uploads/study_materials'
app.secret_key = os.getenv("SECRET_KEY")

# Keep your original upload folder for other features
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')

# Create both directories if they don't exist
os.makedirs(app.config['STUDY_MATERIALS_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database Connection Helper
def get_db_connection():
    try:
        conn = pymysql.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=True,
)
        return conn
    except pymysql.MySQLError as e:
        print(f"Database Error: {e}")
        return None

# --- AUTHENTICATION MODULE ---

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        if conn is None:
            flash("Database Connection failed!","danger")
            return redirect(url_for("login"))
        cursor=conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['name'] = user['name']
            
            # Safely get the role, defaulting to 'student' if column is missing
            user_role = user.get('role', 'student')
            session['role'] = user_role
            
            # Use the safe variable here instead of user['role']
            if user_role == 'admin':
             return redirect(url_for('admin_portal'))
            else:
             return redirect(url_for('home'))
        else:
            flash('Invalid Username or Password!', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- STUDENT MODULE ---
@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if request.method == 'POST':
        username = request.form['username']
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # 1. Check if new passwords match
        if new_password != confirm_password:
            flash('New Password and Confirm Password do not match!', 'danger')
            return redirect(url_for('change_password'))

        if old_password == new_password:
            flash('New password cannot be the same as your old password!', 'danger')
            return redirect(url_for('change_password'))

        conn = get_db_connection()
        if conn is None:
            flash("Database Connection failed!", "danger")
            return redirect(url_for("change_password"))
            
        cursor = conn.cursor()
        cursor.execute("SELECT id, password, last_password_change FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        # 2. Verify User and Old Password
        if not user:
            cursor.close()
            conn.close()
            flash('Username not found!', 'danger')
            return redirect(url_for('change_password'))

        if old_password != user['password']:
            cursor.close()
            conn.close()
            flash('Incorrect Old Password!', 'danger')
            return redirect(url_for('change_password'))

        # 3. Enforce 30-Day (1 Month) Restriction
        last_change = user['last_password_change']
        if last_change:
            days_since_change = (datetime.now() - last_change).days
            if days_since_change < 30:
                days_left = 30 - days_since_change
                cursor.close()
                conn.close()
                flash(f'Password change restricted! You can change your password again in {days_left} day(s).', 'danger')
                return redirect(url_for('change_password'))

        # 4. Update Password and Timestamp
        cursor.execute("""
            UPDATE users 
            SET password = %s, last_password_change = %s 
            WHERE id = %s
        """, (new_password, datetime.now(), user['id']))
        
        conn.commit()
        cursor.close()
        conn.close()

        flash('Password successfully changed! Please log in with your new password.', 'success')
        return redirect(url_for('login'))

    return render_template('change_password.html')
@app.route("/home")
def home():

    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    student_id = session['user_id']

    conn = get_db_connection()

    if conn is None:
        flash("Database Connection Failed!", "danger")
        return redirect(url_for('login'))

    cursor = conn.cursor()

    # Attendance Statistics
    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(status='P') AS present
        FROM attendance_phase1
        WHERE student_id=%s
    """, (student_id,))

    attendance_data = cursor.fetchone()

    total = attendance_data["total"] or 0
    present = attendance_data["present"] or 0

    attendance = round((present / total) * 100) if total > 0 else 0

    # Total Assignments
    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM assignments
    """)

    assignments = cursor.fetchone()["total"]

    # Internal Marks Subjects
    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM phase1_marks
        WHERE student_id=%s
    """, (student_id,))

    marks = cursor.fetchone()["total"]

    cursor.close()
    conn.close()

    return render_template(
        "home.html",
        attendance=attendance,
        assignments=assignments,
        marks=marks
    )

@app.route('/attendance')
def student_attendance():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
        
    student_id = session['user_id']
    conn = get_db_connection()
    if conn is None:
        flash("Database Connection Failed!", "danger")
        return redirect(url_for("login"))
    cursor = conn.cursor()
    
    # Detailed log
    cursor.execute("SELECT * FROM attendance_phase1 WHERE student_id = %s ORDER BY attendance_date DESC", (student_id,))
    logs = cursor.fetchall()
    
    # Summary Calculations
    total_classes = len(logs)
    total_present = sum(1 for log in logs if log['status'] == 'P')
    total_absent = total_classes - total_present
    overall_percentage = round((total_present / total_classes * 100)) if total_classes > 0 else 0
    
    # Course-wise summary
    course_summary = {}
    for log in logs:
        code = log['course_code']
        if code not in course_summary:
            course_summary[code] = {'present': 0, 'absent': 0, 'total': 0}
        course_summary[code]['total'] += 1
        if log['status'] == 'P':
            course_summary[code]['present'] += 1
        else:
            course_summary[code]['absent'] += 1
            
    for code, stats in course_summary.items():
        stats['percentage'] = round((stats['present'] / stats['total']) * 100)
        
    cursor.close()
    conn.close()
    
    return render_template('student_attendance.html', 
                           total_classes=total_classes, total_present=total_present,
                           total_absent=total_absent, overall_percentage=overall_percentage,
                           course_summary=course_summary, logs=logs)

@app.route('/assignments', methods=['GET', 'POST'])
def student_assignments():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
        
    student_id = session['user_id']
    conn = get_db_connection()
    if conn is None:
        flash("Database Connection Failed!", "danger")
        return redirect(url_for("login"))
    cursor = conn.cursor()
    
    if request.method == 'POST' and 'file' in request.files:
        file = request.files['file']
        assignment_id = request.form['assignment_id']
        if file and file.filename != '':
            filename = f"Student_{student_id}_Assign_{assignment_id}_{int(datetime.now().timestamp())}.pdf"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            cursor.execute("""
                INSERT INTO assignment_submissions (assignment_id, student_id, submission_link)
                VALUES (%s, %s, %s)
            """, (assignment_id, student_id, f"uploads/{filename}"))
            conn.commit()
            flash("Assignment submitted successfully!", "success")
            return redirect(url_for('student_assignments'))

    # Fetch assignments and student's submission status
    cursor.execute("""
        SELECT a.*, s.submission_id, s.submission_link, s.marks_awarded, s.submitted_at
        FROM assignments a
        LEFT JOIN assignment_submissions s ON a.id = s.assignment_id AND s.student_id = %s
        ORDER BY a.deadline ASC
    """, (student_id,))
    assignments = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template(
    "student_assignments.html",
    assignments=assignments,
    now=datetime.now()
)
@app.route("/lms")
def lms():
    return render_template("lms.html")
@app.route("/java-course")
def java_course():

    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    return render_template("java_course.html")
@app.route("/data_structures-course")
def dsa_course():

    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    return render_template("data_structures.html")
@app.route("/adv_dsa")
def adv_dsa_course():

    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    return render_template("adv_dsa.html")
@app.route("/Ai")
def Ai_course():

    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    return render_template("Ai.html")
@app.route('/announcements')
def announcements():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    webinars = [
        {
            "title": "Data Analytics using Python",
            "date": "18 July 2026",
            "time": "4:00 PM - 6:30 PM",
            "credits": 1,
            "icon": "fa-chart-line",
            "color": "blue"
        },
        {
            "title": "Web Development",
            "date": "26 July 2026",
            "time": "4:00 PM - 7:00 PM",
            "credits": 1,
            "icon": "fa-code",
            "color": "green"
        },
        {
            "title": "AI Tools & Technologies",
            "date": "30 July 2026",
            "time": "8:00 PM - 9:30 PM",
            "credits": 1,
            "icon": "fa-robot",
            "color": "purple"
        },
        {
            "title": "API Creation & Integration",
            "date": "02 August 2026",
            "time": "7:30 PM - 9:30 PM",
            "credits": 1,
            "icon": "fa-plug",
            "color": "orange"
        }
    ]

    return render_template(
        "announcement.html",
        webinars=webinars
    )
# ... your other routes might be up here ...

@app.route('/course/<course_code>/study-materials')
def study_materials(course_code):
    # TODO: In a complete system, query your MySQL database here to get the filename
    # Example: pdf_filename = db.execute("SELECT pdf_file FROM materials WHERE course_code = %s", (course_code,))
    
    # For now, assuming the admin uploaded a file named 'java_notes.pdf' for CSP0101
    pdf_filename = "java_notes.pdf" 
    
    return render_template('study_materials.html', 
                           course_code=course_code, 
                           pdf_filename=pdf_filename)

# ... more of your routes down here ...

@app.route("/internal_marks")
def internal_marks():

    # Only students can access internal marks
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    student_id = session['user_id']

    # Get selected evaluation component
    selected_type = request.args.get("type")

    marks = []

    # Allowed database columns
    allowed_columns = {
        "class_participation": "class_participation",
        "progressive_eval": "progressive_eval",
        "internal_viva": "internal_viva",
        "mid_term_1": "mid_term_1",
        "mid_term_2": "mid_term_2"
    }

    if selected_type and selected_type in allowed_columns:

        column = allowed_columns[selected_type]

        conn = get_db_connection()

        if conn is None:
            flash("Database Connection Failed!", "danger")
            return redirect(url_for("home"))

        cursor = conn.cursor()

        # IMPORTANT:
        # Only show courses where the selected evaluation
        # component actually exists.
        query = f"""
            SELECT
                course_code,
                {column} AS marks
            FROM phase1_marks
            WHERE student_id = %s
              AND {column} IS NOT NULL
            ORDER BY course_code
        """

        cursor.execute(query, (student_id,))

        marks = cursor.fetchall()

        cursor.close()
        conn.close()

    return render_template(
        "internal_marks.html",
        marks=marks,
        selected_type=selected_type
    )

@app.route('/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- ADMIN MODULE ---

# --- ADMIN MODULE ---

@app.route('/admin', methods=['GET'])
def admin_portal():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    if conn is None:
        flash("Database Connection Failed!", "danger")
        return redirect(url_for("login"))
    cursor = conn.cursor()
    
    # Fetch students for attendance tab
    cursor.execute("SELECT id, name FROM users WHERE role = 'student'")
    students = cursor.fetchall()
    
    # Fetch assignments for review tab
    cursor.execute("SELECT * FROM assignments ORDER BY created_at DESC")
    assignments = cursor.fetchall()
    
    # Selected assignment submissions for grading
    selected_assign_id = request.args.get('assign_id')
    submissions = []
    if selected_assign_id:
        cursor.execute("""
            SELECT s.*, u.name, a.max_marks 
            FROM assignment_submissions s
            JOIN users u ON s.student_id = u.id
            JOIN assignments a ON s.assignment_id = a.id
            WHERE s.assignment_id = %s
        """, (selected_assign_id,))
        submissions = cursor.fetchall()
        
    # Fetch quizzes for the Manage Quizzes tab
    cursor.execute("SELECT * FROM quizzes ORDER BY created_at DESC")
    admin_quizzes = cursor.fetchall()
        
    cursor.close()
    conn.close()
    
    return render_template('admin_portal.html', students=students, assignments=assignments, 
                           submissions=submissions, selected_assign_id=selected_assign_id, 
                           admin_quizzes=admin_quizzes, datetime=datetime)

@app.route('/admin/save_attendance', methods=['POST'])
def save_attendance():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    course_code = request.form['course_code']
    date = request.form['date']
    marked_by = session['name']
    
    conn = get_db_connection()
    if conn is None:
        flash("Database Connection Failed!", "danger")
        return redirect(url_for("login"))
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE role = 'student'")
    students = cursor.fetchall()
    
    for student in students:
        sid = str(student['id'])
        status = 'P' if f"present_{sid}" in request.form else 'A'
        cursor.execute("""
            INSERT INTO attendance_phase1 (student_id, course_code, status, marked_by, attendance_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (sid, course_code, status, marked_by, date))
        
    conn.commit()
    cursor.close()
    conn.close()
    flash("Daily Attendance saved successfully!", "success")
    return redirect(url_for('admin_portal'))

@app.route('/admin/create_assignment', methods=['POST'])
def create_assignment():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    title = request.form['title']
    course_code = request.form['course_code']
    max_marks = request.form['max_marks']
    deadline = request.form['deadline']
    description = request.form['description']
    
    conn = get_db_connection()
    if conn is None:
        flash("Database Connection Failed!", "danger")
        return redirect(url_for("login"))
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO assignments (title, course_code, description, max_marks, deadline)
        VALUES (%s, %s, %s, %s, %s)
    """, (title, course_code, description, max_marks, deadline))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash("New Assignment published!", "success")
    return redirect(url_for('admin_portal'))

@app.route('/admin/grade_submission', methods=['POST'])
def grade_submission():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    submission_id = request.form['submission_id']
    marks = request.form['marks']
    assign_id = request.form['assign_id']
    
    conn = get_db_connection()
    if conn is None:
         flash("Database Connection Failed!", "danger")
         return redirect(url_for("login"))
    cursor = conn.cursor()
    cursor.execute("UPDATE assignment_submissions SET marks_awarded = %s WHERE submission_id = %s", (marks, submission_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash("Grade updated!", "success")
    return redirect(url_for('admin_portal', assign_id=assign_id))

# ==========================================
# --- QUIZ MODULE (STUDENT & ADMIN) ---
# ==========================================

@app.route('/quizzes')
def quiz_dashboard():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all active quizzes
    cursor.execute("SELECT * FROM quizzes WHERE is_active = TRUE")
    quizzes = cursor.fetchall()

    # Check which quizzes the student has already submitted
    for quiz in quizzes:
        cursor.execute("""
            SELECT score, total_questions 
            FROM quiz_submissions 
            WHERE quiz_id = %s AND student_id = %s
        """, (quiz['id'], session['user_id']))
        submission = cursor.fetchone()
        
        if submission:
            quiz['has_submitted'] = True
            quiz['score'] = submission['score']
            quiz['total_questions'] = submission['total_questions']
        else:
            quiz['has_submitted'] = False

    cursor.close()
    conn.close()
    return render_template('quiz.html', view='list', quizzes=quizzes)


@app.route('/quizzes/<int:quiz_id>')
def take_quiz(quiz_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Security check: Ensure student hasn't already submitted this quiz
    cursor.execute("SELECT id FROM quiz_submissions WHERE quiz_id = %s AND student_id = %s", (quiz_id, session['user_id']))
    if cursor.fetchone():
        flash("You have already submitted this quiz. You cannot take it twice.", "danger")
        return redirect(url_for('quiz_dashboard'))

    # Fetch quiz details
    cursor.execute("SELECT * FROM quizzes WHERE id = %s", (quiz_id,))
    quiz = cursor.fetchone()

    # Fetch questions (excluding the correct answer so it isn't sent to the browser)
    cursor.execute("SELECT id, question_text, opt_a, opt_b, opt_c, opt_d FROM questions WHERE quiz_id = %s", (quiz_id,))
    questions = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('take_quiz.html', quiz=quiz, questions=questions)


@app.route('/quizzes/<int:quiz_id>/submit', methods=['POST'])
def submit_quiz(quiz_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch correct answers to grade the test
    cursor.execute("SELECT id, correct_opt FROM questions WHERE quiz_id = %s", (quiz_id,))
    questions = cursor.fetchall()

    score = 0
    total_questions = len(questions)

    # Loop through each question and check the submitted answer
    for q in questions:
        student_answer = request.form.get(f"q_{q['id']}")
        if student_answer == q['correct_opt']:
            score += 1

    # Save final score to database
    cursor.execute("""
        INSERT INTO quiz_submissions (quiz_id, student_id, score, total_questions)
        VALUES (%s, %s, %s, %s)
    """, (quiz_id, session['user_id'], score, total_questions))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Quiz submitted successfully! Marks will be displayed once the Admin releases them.", "success")
    return redirect(url_for('quiz_dashboard'))


@app.route('/admin/create_quiz', methods=['POST'])
def admin_create_quiz():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    title = request.form['title']
    course_code = request.form['course_code']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO quizzes (title, course_code) VALUES (%s, %s)", (title, course_code))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Quiz Framework created! You can now add questions to it via the database.", "success")
    return redirect(url_for('admin_portal'))


@app.route('/admin/toggle_quiz_results', methods=['POST'])
def admin_toggle_quiz_results():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    quiz_id = request.form['quiz_id']

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Toggle the boolean true/false
    cursor.execute("UPDATE quizzes SET results_released = NOT results_released WHERE id = %s", (quiz_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Quiz marks visibility updated for students!", "success")
    return redirect(url_for('admin_portal'))
@app.route('/admin/add_question', methods=['POST'])
def admin_add_question():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    quiz_id = request.form['quiz_id']
    question_text = request.form['question_text']
    opt_a = request.form['opt_a']
    opt_b = request.form['opt_b']
    opt_c = request.form['opt_c']
    opt_d = request.form['opt_d']
    correct_opt = request.form['correct_opt']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO questions (quiz_id, question_text, opt_a, opt_b, opt_c, opt_d, correct_opt)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (quiz_id, question_text, opt_a, opt_b, opt_c, opt_d, correct_opt))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Question added to the quiz successfully!", "success")
    return redirect(url_for('admin_portal'))

if __name__ == "__main__":
    app.run(debug=False)