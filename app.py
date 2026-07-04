import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import pymysql
import pymysql.cursors
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
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
                return redirect(url_for('student_attendance'))
        else:
            flash('Invalid Username or Password!', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- STUDENT MODULE ---

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
    return render_template('student_assignments.html', assignments=assignments)

@app.route('/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

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
        
    cursor.close()
    conn.close()
    
    # ---> ADD datetime=datetime TO THIS LINE BELOW <---
    return render_template('admin_portal.html', students=students, assignments=assignments, 
                           submissions=submissions, selected_assign_id=selected_assign_id, datetime=datetime)

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

if __name__ == "__main__":
    app.run(debug=False)