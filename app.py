import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import pymysql
import pymysql.cursors
from dotenv import load_dotenv
import requests
from flask import request, jsonify
from zoneinfo import ZoneInfo


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


    # =====================================================
    # 1. PHASE-1 ATTENDANCE
    # =====================================================

    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(status = 'P') AS present
        FROM attendance_phase1
        WHERE student_id = %s
    """, (student_id,))

    attendance_data = cursor.fetchone()

    total = attendance_data["total"] or 0
    present = attendance_data["present"] or 0

    attendance = (
        round((present / total) * 100)
        if total > 0
        else 0
    )


    # =====================================================
    # 2. PHASE-2 ATTENDANCE
    # Used for Tournament Eligibility
    # =====================================================

    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(status = 'P') AS present
        FROM phase2_attendance
        WHERE student_id = %s
    """, (student_id,))

    phase2_attendance_data = cursor.fetchone()

    phase2_total = phase2_attendance_data["total"] or 0
    phase2_present = phase2_attendance_data["present"] or 0

    phase2_attendance = (
        round((phase2_present / phase2_total) * 100)
        if phase2_total > 0
        else 0
    )


    # =====================================================
    # 3. TOTAL ASSIGNMENTS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM assignments
    """)

    assignments = cursor.fetchone()["total"] or 0


    # =====================================================
    # 4. INTERNAL MARKS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM phase1_marks
        WHERE student_id = %s
    """, (student_id,))

    marks = cursor.fetchone()["total"] or 0


    # =====================================================
    # 5. TOURNAMENTS ENROLLED
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS total_enrolled
        FROM tournament_registrations
        WHERE student_id = %s
          AND registration_status = 'Registered'
    """, (student_id,))

    tournament_enrolled_data = cursor.fetchone()

    total_tournaments = (
        tournament_enrolled_data["total_enrolled"]
        or 0
    )


    # =====================================================
    # 6. TOURNAMENTS WON
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS total_won
        FROM tournament_registrations
        WHERE student_id = %s
          AND registration_status = 'Registered'
          AND result = 'Winner'
    """, (student_id,))

    tournament_won_data = cursor.fetchone()

    tournaments_won = (
        tournament_won_data["total_won"]
        or 0
    )


    # =====================================================
    # 7. TOURNAMENT WIN RATE
    # =====================================================

    if total_tournaments > 0:

        tournament_win_rate = round(
            (tournaments_won / total_tournaments) * 100,
            1
        )

    else:

        tournament_win_rate = 0


    # =====================================================
    # 8. UPCOMING TOURNAMENT
    #
    # Only show tournaments whose:
    # - tournament date has not passed
    # - registration deadline has not passed
    #
    # TIME_FORMAT is used because MySQL TIME fields can
    # arrive in Python as datetime.timedelta.
    # =====================================================

    cursor.execute("""
        SELECT
            t.*,

            TIME_FORMAT(
                t.start_time,
                '%%h:%%i %%p'
            ) AS formatted_start_time,

            DATE_FORMAT(
                t.registration_deadline,
                '%%d %%b %%Y, %%h:%%i %%p'
            ) AS formatted_registration_deadline

        FROM tournaments t

        WHERE t.tournament_date >= CURDATE()

          AND t.registration_deadline > NOW()

        ORDER BY
            t.tournament_date ASC,
            t.start_time ASC

        LIMIT 1
    """)

    upcoming_tournaments = cursor.fetchall()


    # =====================================================
    # 9. CLOSE DATABASE
    # =====================================================

    cursor.close()
    conn.close()


    # =====================================================
    # 10. RENDER DASHBOARD
    # =====================================================

    return render_template(
        "home.html",

        # Existing dashboard values
        attendance=attendance,
        assignments=assignments,
        marks=marks,

        # Phase-2 attendance
        phase2_attendance=phase2_attendance,

        # Tournament statistics
        total_tournaments=total_tournaments,
        tournaments_won=tournaments_won,
        tournament_win_rate=tournament_win_rate,

        # Upcoming tournament
        upcoming_tournaments=upcoming_tournaments
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

    # --- NEW DYNAMIC LOGIC STARTS HERE ---
    # URL se phase ki value pakdo (Agar koi value nahi hai toh default '1' mano)
    phase = request.args.get('phase', '1')

    # Phase ke hisaab se SQL query decide karo
    if phase == '2':
        query = "SELECT * FROM phase2_attendance WHERE student_id = %s ORDER BY attendance_date DESC"
    else:
        query = "SELECT * FROM attendance_phase1 WHERE student_id = %s ORDER BY attendance_date DESC"
    
    # Decide ki gayi query ko execute karo
    cursor.execute(query, (student_id,))
    # --- NEW DYNAMIC LOGIC ENDS HERE ---

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
# =========================================================
# TOURNAMENT MODULE
# =========================================================

@app.route('/tournaments')
def tournaments():

    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    student_id = session['user_id']

    conn = get_db_connection()

    if conn is None:
        flash("Database Connection Failed!", "danger")
        return redirect(url_for('home'))

    cursor = conn.cursor()

    try:

        # -------------------------------------------------
        # Calculate student's Phase-2 attendance
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*) AS total_classes,
                COALESCE(
                    SUM(
                        CASE
                            WHEN UPPER(status) = 'P'
                            THEN 1
                            ELSE 0
                        END
                    ), 0
                ) AS present_classes
            FROM phase2_attendance
            WHERE student_id = %s
        """, (student_id,))

        attendance_data = cursor.fetchone()

        total_classes = attendance_data['total_classes'] or 0
        present_classes = attendance_data['present_classes'] or 0

        if total_classes > 0:
            attendance_percentage = round(
                (present_classes / total_classes) * 100,
                2
            )
        else:
            attendance_percentage = 0


        # -------------------------------------------------
        # Fetch tournaments
        # -------------------------------------------------

        cursor.execute("""
    SELECT
        t.*,

        DATE_FORMAT(t.start_time, '%%h:%%i %%p')
            AS formatted_start_time,

        CASE
            WHEN t.registration_deadline > %s
            THEN 1
            ELSE 0
        END AS registration_open,

        CASE
            WHEN tr.registration_id IS NOT NULL
            THEN 1
            ELSE 0
        END AS already_registered

    FROM tournaments t

    LEFT JOIN tournament_registrations tr
        ON t.tournament_id = tr.tournament_id
        AND tr.student_id = %s
        AND tr.registration_status = 'Registered'

    WHERE t.status IN ('Upcoming', 'Ongoing')

    ORDER BY
        t.tournament_date ASC,
        t.start_time ASC
""", (
    datetime.now(),
    student_id
))

        tournament_list = cursor.fetchall()

        # Add attendance to every tournament
        for tournament in tournament_list:
            tournament['attendance_percentage'] = attendance_percentage


    except Exception as e:

        print("Tournament Error:", e)

        flash(
            "Unable to load tournaments.",
            "danger"
        )

        tournament_list = []

    finally:

        cursor.close()
        conn.close()


    return render_template(
        'tournament.html',
        tournaments=tournament_list
    )
@app.route(
    '/tournament/<int:tournament_id>/register',
    methods=['POST']
)
def register_tournament(tournament_id):

    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    student_id = session['user_id']

    conn = get_db_connection()

    if conn is None:
        flash(
            "Database Connection Failed!",
            "danger"
        )
        return redirect(url_for('tournaments'))

    cursor = conn.cursor()

    try:

        # -------------------------------------------------
        # 1. Get tournament
        # -------------------------------------------------

        cursor.execute("""
            SELECT *
            FROM tournaments
            WHERE tournament_id = %s
        """, (tournament_id,))

        tournament = cursor.fetchone()

        if not tournament:

            flash(
                "Tournament not found.",
                "danger"
            )

            return redirect(url_for('tournaments'))


        # -------------------------------------------------
        # 2. Check tournament status
        # -------------------------------------------------

        if tournament['status'] not in ['Upcoming', 'Ongoing']:

            flash(
                "This tournament is not open for registration.",
                "warning"
            )

            return redirect(url_for('tournaments'))


        # -------------------------------------------------
        # 3. Check registration deadline
        # -------------------------------------------------

        current_time = datetime.now()

        if current_time > tournament['registration_deadline']:

            flash(
                "Registration deadline has expired.",
                "danger"
            )

            return redirect(url_for('tournaments'))


        # -------------------------------------------------
        # 4. Check duplicate registration
        # -------------------------------------------------

        cursor.execute("""
            SELECT registration_id
            FROM tournament_registrations
            WHERE tournament_id = %s
              AND student_id = %s
              AND registration_status = 'Registered'
        """, (
            tournament_id,
            student_id
        ))

        existing_registration = cursor.fetchone()

        if existing_registration:

            flash(
                "You are already registered for this tournament.",
                "info"
            )

            return redirect(url_for('tournaments'))


        # -------------------------------------------------
        # 5. Calculate Phase-2 Attendance
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*) AS total_classes,

                COALESCE(
                    SUM(
                        CASE
                            WHEN UPPER(status) = 'P'
                            THEN 1
                            ELSE 0
                        END
                    ), 0
                ) AS present_classes

            FROM phase2_attendance

            WHERE student_id = %s
        """, (student_id,))

        attendance_data = cursor.fetchone()

        total_classes = attendance_data['total_classes'] or 0
        present_classes = attendance_data['present_classes'] or 0


        # -------------------------------------------------
        # 6. Calculate percentage
        # -------------------------------------------------

        if total_classes > 0:

            attendance_percentage = round(
                (present_classes / total_classes) * 100,
                2
            )

        else:

            attendance_percentage = 0


        # -------------------------------------------------
        # 7. Check 80% requirement
        # -------------------------------------------------

        if attendance_percentage < float(
            tournament['min_attendance']
        ):

            flash(
                f"Registration failed. "
                f"Your Phase-2 attendance is "
                f"{attendance_percentage}%. "
                f"Minimum required attendance is "
                f"{tournament['min_attendance']}%.",
                "danger"
            )

            return redirect(url_for('tournaments'))


        # -------------------------------------------------
        # 8. Register Student
        # -------------------------------------------------

        cursor.execute("""
            INSERT INTO tournament_registrations
            (
                tournament_id,
                student_id,
                attendance_percentage,
                registration_status
            )

            VALUES
            (
                %s,
                %s,
                %s,
                'Registered'
            )
        """, (
            tournament_id,
            student_id,
            attendance_percentage
        ))


        conn.commit()


        flash(
            f"Successfully registered for "
            f"{tournament['title']}!",
            "success"
        )


    except pymysql.IntegrityError:

        conn.rollback()

        flash(
            "You are already registered for this tournament.",
            "warning"
        )


    except Exception as e:

        conn.rollback()

        print(
            "Tournament Registration Error:",
            e
        )

        flash(
            "Something went wrong while registering.",
            "danger"
        )


    finally:

        cursor.close()
        conn.close()


    return redirect(url_for('tournaments'))
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
@app.route("/chatbot", methods=["GET", "POST"])
def chatbot():

    if request.method == "GET":
        return render_template("chatbot.html")

    try:
        # Get question from chatbot.html
        data = request.get_json()

        if not data:
            return jsonify({
                "error": "No data received."
            }), 400

        message = data.get("message", "").strip()

        if not message:
            return jsonify({
                "error": "Please enter a question."
            }), 400

        # Get API key from Render Environment Variables
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()

        if not api_key:
            print("OPENROUTER_API_KEY is missing!")

            return jsonify({
                "error": "AI service is not configured."
            }), 500

        # Send request to OpenRouter
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",

            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",

                # Optional but recommended
                "HTTP-Referer": "https://studentportal-rk08.onrender.com",
                "X-Title": "Student Portal AI Assistant"
            },

            json={
                "model": "openrouter/free",

                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an AI Study Assistant "
                            "for a university student portal. "

                            "Answer study-related questions clearly "
                            "and accurately. "

                            "Explain difficult concepts in simple "
                            "language and use examples when helpful. "

                            "You can help with programming, "
                            "Data Structures, Algorithms, "
                            "Machine Learning, Deep Learning, "
                            "NLP, LLMs, SQL, DBMS, mathematics "
                            "and other academic topics."
                        )
                    },
                    {
                        "role": "user",
                        "content": message
                    }
                ],

                "temperature": 0.7,

                "max_tokens": 1000,

                "stream": False
            },

            timeout=120
        )

        # Print error in Render logs if OpenRouter fails
        print(
            "OpenRouter Status:",
            response.status_code
        )

        if response.status_code != 200:

            print(
                "OpenRouter Error:",
                response.text
            )

            return jsonify({
                "error": "AI service returned an error."
            }), 500

        # Convert response to JSON
        result = response.json()

        # Extract AI answer
        answer = (
            result
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )

        if not answer:

            return jsonify({
                "error": "AI did not return a response."
            }), 500

        # Send answer back to chatbot.html
        return jsonify({
            "response": answer
        })

    except requests.exceptions.Timeout:

        return jsonify({
            "error": "AI response timed out. Please try again."
        }), 504

    except requests.exceptions.RequestException as e:

        print(
            "OpenRouter connection error:",
            repr(e)
        )

        return jsonify({
            "error": "Unable to connect to AI service."
        }), 503

    except Exception as e:

        print(
            "Chatbot error:",
            repr(e)
        )

        return jsonify({
            "error": "Something went wrong."
        }), 500
@app.route('/repeater')
def repeater_status():
    # Security check: User logged in hai ya nahi
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    student_id = session['user_id']
    conn = get_db_connection()
    if conn is None:
        flash("Database Connection Failed!", "danger")
        return redirect(url_for("login"))
    
    cursor = conn.cursor()

    # Repeater table se student ka data fetch karna
    cursor.execute("SELECT course_code, failed_id FROM repeater WHERE student_id = %s", (student_id,))
    failed_subjects = cursor.fetchall()
    
    cursor.close()
    conn.close()

    # Data ko repeater.html par bhej do
    return render_template('repeater.html', failed_subjects=failed_subjects)
@app.route('/results')
def result_list():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all marksheets for this student
    cursor.execute("SELECT * FROM marksheet_list WHERE student_id = %s", (student_id,))
    marksheets = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('result_list.html', marksheets=marksheets)


@app.route('/view_marksheet/<int:marksheet_id>')
def view_marksheet(marksheet_id):
    # Check if user is logged in
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor() # Ensure 'dictionary=True' nahi hataya hai (Sirf in dono naye routes par 'dictionary=True' chahiye hota hai kyunki hum marksheet['item'] aise likh rahe hain)

    # 1. Fetch marksheet WITH SECURITY CHECK (Sirf wahi marksheet laao jiska id aur student_id dono match hon)
    cursor.execute("SELECT * FROM marksheet_list WHERE id = %s AND student_id = %s", (marksheet_id, student_id))
    marksheet = cursor.fetchone()

    # Agar marksheet nahi mili, iska matlab student kisi aur ka result URL change karke dekhne ki koshish kar raha hai
    if not marksheet:
        cursor.close()
        conn.close()
        return "Unauthorized Access! Yeh result aapka nahi hai.", 403

    # 2. Fetch all subjects for this marksheet
    cursor.execute("SELECT * FROM marksheet_details WHERE marksheet_id = %s", (marksheet_id,))
    subjects = cursor.fetchall()
    
    # 3. Fetch User Details strictly using current session ID
    cursor.execute("SELECT * FROM users WHERE id = %s", (student_id,))
    user_info = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template('detailed_marksheet.html', marksheet=marksheet, subjects=subjects, user_info=user_info)
import os
from werkzeug.utils import secure_filename

# 1. View & Edit Profile Route
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        phone = request.form.get('phone')
        dob = request.form.get('dob')
        gender = request.form.get('gender')
        course = request.form.get('course')
        branch = request.form.get('branch')
        semester = request.form.get('semester')
        university = request.form.get('university')
        bio = request.form.get('bio')
        skills = request.form.get('skills')
        github = request.form.get('github')
        linkedin = request.form.get('linkedin')

        # Handle Profile Photo Upload
        photo_filename = None
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename != '':
                photo_filename = secure_filename(file.filename)
                upload_folder = os.path.join('static', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                file.save(os.path.join(upload_folder, photo_filename))

        # Check if profile exists, update or insert
        cursor.execute("SELECT id FROM student_profiles WHERE student_id = %s", (student_id,))
        existing = cursor.fetchone()

        if existing:
            if photo_filename:
                cursor.execute("""
                    UPDATE student_profiles SET phone=%s, date_of_birth=%s, gender=%s, course=%s, 
                    branch=%s, semester=%s, university=%s, profile_photo=%s, bio=%s, skills=%s, github=%s, linkedin=%s 
                    WHERE student_id=%s
                """, (phone, dob, gender, course, branch, semester, university, photo_filename, bio, skills, github, linkedin, student_id))
            else:
                cursor.execute("""
                    UPDATE student_profiles SET phone=%s, date_of_birth=%s, gender=%s, course=%s, 
                    branch=%s, semester=%s, university=%s, bio=%s, skills=%s, github=%s, linkedin=%s 
                    WHERE student_id=%s
                """, (phone, dob, gender, course, branch, semester, university, bio, skills, github, linkedin, student_id))
        else:
            cursor.execute("""
                INSERT INTO student_profiles (student_id, phone, date_of_birth, gender, course, branch, semester, university, profile_photo, bio, skills, github, linkedin, rp_points)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            """, (student_id, phone, dob, gender, course, branch, semester, university, photo_filename, bio, skills, github, linkedin))
        
        conn.commit()
        cursor.close()
        conn.close()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('profile'))

    # Fetch Profile & User Details + RP History
    cursor.execute("SELECT * FROM users WHERE id = %s", (student_id,))
    user = cursor.fetchone()

    cursor.execute("SELECT * FROM student_profiles WHERE student_id = %s", (student_id,))
    profile_data = cursor.fetchone()

    cursor.execute("SELECT * FROM rp_transactions WHERE student_id = %s ORDER BY created_at DESC", (student_id,))
    rp_history = cursor.fetchall()
    # -------------------------------------------------
# TOURNAMENT STATISTICS
# -------------------------------------------------

# Total tournaments enrolled
    cursor.execute("""
        SELECT COUNT(*) AS total_enrolled
        FROM tournament_registrations
        WHERE student_id = %s
        AND registration_status = 'Registered'
    """, (student_id,))

    tournament_stats = cursor.fetchone()

    total_tournaments = tournament_stats['total_enrolled'] or 0


    # Total tournaments won
    cursor.execute("""
        SELECT COUNT(*) AS total_won
        FROM tournament_registrations
        WHERE student_id = %s
        AND registration_status = 'Registered'
        AND result = 'Winner'
    """, (student_id,))

    win_data = cursor.fetchone()

    tournaments_won = win_data['total_won'] or 0


    # Win percentage
    if total_tournaments > 0:
        tournament_win_rate = round(
            (tournaments_won / total_tournaments) * 100,
            1
        )
    else:
        tournament_win_rate = 0


    # Recent tournament history
    cursor.execute("""
        SELECT
            t.tournament_id,
            t.title,
            t.tournament_date,
            t.venue,
            tr.attendance_percentage,
            tr.result,
            tr.registered_at

        FROM tournament_registrations tr

        INNER JOIN tournaments t
            ON tr.tournament_id = t.tournament_id

        WHERE tr.student_id = %s
        AND tr.registration_status = 'Registered'

        ORDER BY tr.registered_at DESC
    """, (student_id,))

    tournament_history = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
    'profile.html',
    user=user,
    profile=profile_data,
    rp_history=rp_history,

    total_tournaments=total_tournaments,
    tournaments_won=tournaments_won,
    tournament_win_rate=tournament_win_rate,
    tournament_history=tournament_history
)


# 2. Game Center Dashboard
@app.route('/games')
def game_center():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Active games fetch karo
    cursor.execute("SELECT * FROM games WHERE status = 'active'")
    games = cursor.fetchall()

    # Get student RP
    cursor.execute("SELECT rp_points FROM student_profiles WHERE student_id = %s", (student_id,))
    p_data = cursor.fetchone()
    student_rp = p_data['rp_points'] if p_data else 0

    # Find out which games this student has already completed
    cursor.execute("SELECT game_id FROM game_attempts WHERE student_id = %s AND status = 'completed'", (student_id,))
    completed_games = {row['game_id'] for row in cursor.fetchall()}

    cursor.close()
    conn.close()

    return render_template('game_center.html', games=games, student_rp=student_rp, completed_games=completed_games)


# 3. Play Game Route
@app.route('/game/<int:game_id>')
def play_game(game_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM games WHERE id = %s AND status = 'active'", (game_id,))
    game = cursor.fetchone()
    if not game:
        flash("Game not available or inactive.", "danger")
        return redirect(url_for('game_center'))

    # Check if already completed and replay is not allowed
    if not game['allow_replay']:
        cursor.execute("SELECT * FROM game_attempts WHERE student_id = %s AND game_id = %s AND status = 'completed'", (student_id, game_id))
        if cursor.fetchone():
            flash("You have already completed this game!", "warning")
            return redirect(url_for('game_center'))

    cursor.execute("SELECT id, question_text, option_a, option_b, option_c, option_d, question_order FROM game_questions WHERE game_id = %s ORDER BY question_order ASC", (game_id,))
    questions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('play_game.html', game=game, questions=questions)


@app.route('/game/<int:game_id>/submit', methods=['POST'])
def submit_game(game_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM games WHERE id = %s", (game_id,))
    game = cursor.fetchone()
    if not game:
        return redirect(url_for('game_center'))

    # Fetch questions and correct options from DB (Secure Server-side check)
    cursor.execute("SELECT id, correct_option, rp_points FROM game_questions WHERE game_id = %s", (game_id,))
    questions = {q['id']: q for q in cursor.fetchall()}

    correct_answers = 0
    total_questions = len(questions)
    rp_earned = 0

    for q_id, q_data in questions.items():
        user_answer = request.form.get(f'question_{q_id}')
        if user_answer and user_answer.upper() == q_data['correct_option']:
            correct_answers += 1
            rp_earned += q_data['rp_points']

    try:
        # 1. Ensure student profile entry exists so RP doesn't fail
        cursor.execute("SELECT id FROM student_profiles WHERE student_id = %s", (student_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO student_profiles (student_id, rp_points) VALUES (%s, 0)", (student_id,))

        # 2. Record game attempt
        cursor.execute("""
            INSERT INTO game_attempts (student_id, game_id, total_questions, correct_answers, rp_earned, status, completed_at)
            VALUES (%s, %s, %s, %s, %s, 'completed', NOW())
        """, (student_id, game_id, total_questions, correct_answers, rp_earned))
        
        attempt_id = cursor.lastrowid

        # 3. Update student RP points
        cursor.execute("UPDATE student_profiles SET rp_points = rp_points + %s WHERE student_id = %s", (rp_earned, student_id))

        # 4. Log transaction history
        if rp_earned > 0:
            cursor.execute("""
                INSERT INTO rp_transactions (student_id, points, transaction_type, reference_id, description)
                VALUES (%s, %s, 'game', %s, %s)
            """, (student_id, rp_earned, attempt_id, f"Completed game: {game['name']}"))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error updating RP: {e}")
    finally:
        cursor.close()
        conn.close()

    return render_template('game_result.html', game=game, correct_answers=correct_answers, total_questions=total_questions, rp_earned=rp_earned)
# 1. View RP Shop
@app.route('/shop')
def rp_shop():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get student RP from student_profiles
    cursor.execute("SELECT rp_points FROM student_profiles WHERE student_id = %s", (student_id,))
    p_data = cursor.fetchone()
    student_rp = p_data['rp_points'] if p_data else 0

    # Create dummy user object for template compatibility
    student_obj = {'rp_points': student_rp}

    # Fetch active shop items
    cursor.execute("SELECT * FROM shop WHERE status = 'active'")
    shop_items = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('shop.html', student=student_obj, shop_items=shop_items)


# 2. Secure Purchase Route (Atomic Update & DB Transaction)
@app.route('/shop/purchase/<int:item_id>', methods=['POST'])
def purchase_shop_item(item_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Fetch item details strictly from DB (Never trust browser data)
        cursor.execute("SELECT * FROM shop WHERE id = %s AND status = 'active'", (item_id,))
        item = cursor.fetchone()
        if not item:
            flash("Invalid or inactive item.", "danger")
            return redirect(url_for('rp_shop'))

        cost = item['rp_cost']

        # Start Transaction & Atomic deduction to prevent race conditions
        cursor.execute("START TRANSACTION")

        # Deduct RP only if student has enough points
        cursor.execute("""
            UPDATE student_profiles 
            SET rp_points = rp_points - %s 
            WHERE student_id = %s AND rp_points >= %s
        """, (cost, student_id, cost))

        if cursor.rowcount == 0:
            cursor.execute("ROLLBACK")
            flash("Not enough RP points to redeem this reward!", "danger")
            return redirect(url_for('rp_shop'))

        # Create Purchase Record
        cursor.execute("""
            INSERT INTO shop_purchases (student_id, shop_item_id, item_name, rp_spent, reward_type, reward_value, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
        """, (student_id, item['id'], item['item_name'], cost, item['reward_type'], item['reward_value']))
        
        purchase_id = cursor.lastrowid

        # Log RP Transaction (Negative points for spending)
        cursor.execute("""
            INSERT INTO rp_transactions (student_id, points, transaction_type, reference_id, description)
            VALUES (%s, %s, 'deduction', %s, %s)
        """, (student_id, -cost, purchase_id, f"Purchased {item['item_name']} from RP Shop"))

        conn.commit()
        flash(f"Successfully redeemed {item['item_name']}! Request sent to administration.", "success")

    except Exception as e:
        conn.rollback()
        flash("An error occurred during purchase. Please try again.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('my_purchases'))


# 3. Student Purchases History
@app.route('/shop/my-purchases')
def my_purchases():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM shop_purchases WHERE student_id = %s ORDER BY purchased_at DESC", (student_id,))
    purchases = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('my_purchases.html', purchases=purchases)


# 4. Admin Shop Requests Dashboard
@app.route('/admin/shop/purchases')
def admin_shop_purchases():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sp.*, u.name as student_name, u.username as roll_no 
        FROM shop_purchases sp
        JOIN users u ON sp.student_id = u.id
        ORDER BY sp.purchased_at DESC
    """)
    purchases = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin_shop.html', purchases=purchases)

@app.route(
    '/admin/tournaments',
    methods=['GET', 'POST']
)
def admin_tournaments():

    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()

    if conn is None:

        flash(
            "Database Connection Failed!",
            "danger"
        )

        return redirect(url_for('admin_portal'))

    cursor = conn.cursor()

    try:

        if request.method == 'POST':

            title = request.form.get('title')
            description = request.form.get('description')
            tournament_format = request.form.get('tournament_format')
            venue = request.form.get('venue')
            tournament_date = request.form.get('tournament_date')
            start_time = request.form.get('start_time')
            registration_deadline = request.form.get(
                'registration_deadline'
            )

            min_attendance = request.form.get(
                'min_attendance',
                '80'
            )


            # Validate required fields

            if not title or not description:
                flash(
                    "Title and description are required.",
                    "danger"
                )

                return redirect(
                    url_for('admin_tournaments')
                )


            # Convert deadline from HTML datetime-local

            deadline_datetime = datetime.strptime(
                registration_deadline,
                '%Y-%m-%dT%H:%M'
            )


            # Insert tournament

            cursor.execute("""
                INSERT INTO tournaments
                (
                    title,
                    description,
                    tournament_format,
                    venue,
                    tournament_date,
                    start_time,
                    registration_deadline,
                    min_attendance,
                    status,
                    created_by
                )

                VALUES
                (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, 'Upcoming', %s
                )
            """, (
                title,
                description,
                tournament_format,
                venue,
                tournament_date,
                start_time,
                deadline_datetime,
                min_attendance,
                session['user_id']
            ))


            conn.commit()


            flash(
                "Tournament created successfully!",
                "success"
            )

            return redirect(
                url_for('admin_tournaments')
            )


        # Fetch tournaments for admin

        cursor.execute("""
    SELECT
        t.*,
        u.name AS admin_name,
        DATE_FORMAT(t.start_time, '%%h:%%i %%p') AS formatted_start_time

    FROM tournaments t

    LEFT JOIN users u
        ON t.created_by = u.id

    ORDER BY
        t.tournament_date ASC,
        t.start_time ASC
""")

        tournaments_list = cursor.fetchall()


    except Exception as e:

        conn.rollback()

        print(
            "Admin Tournament Error:",
            e
        )

        flash(
            "Unable to process tournament.",
            "danger"
        )

        tournaments_list = []


    finally:

        cursor.close()
        conn.close()


    return render_template(
        'admin_tournaments.html',
        tournaments=tournaments_list
    )

# 5. Admin Approve Purchase
@app.route('/admin/shop/purchase/<int:purchase_id>/approve', methods=['POST'])
def admin_approve_purchase(purchase_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE shop_purchases SET status = 'approved' WHERE id = %s", (purchase_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Purchase request approved.", "success")
    return redirect(url_for('admin_shop_purchases'))


# 6. Admin Reject Purchase (with Refund)
@app.route('/admin/shop/purchase/<int:purchase_id>/reject', methods=['POST'])
def admin_reject_purchase(purchase_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    admin_note = request.form.get('admin_note', 'Rejected by admin')
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("START TRANSACTION")

        # Get purchase details for refund
        cursor.execute("SELECT * FROM shop_purchases WHERE id = %s AND status = 'pending'", (purchase_id,))
        purchase = cursor.fetchone()

        if purchase:
            # Update status
            cursor.execute("UPDATE shop_purchases SET status = 'rejected', admin_note = %s WHERE id = %s", (admin_note, purchase_id))

            # Refund RP points to student
            cursor.execute("UPDATE student_profiles SET rp_points = rp_points + %s WHERE student_id = %s", (purchase['rp_spent'], purchase['student_id']))

            # Log refund transaction
            cursor.execute("""
                INSERT INTO rp_transactions (student_id, points, transaction_type, reference_id, description)
                VALUES (%s, %s, 'bonus', %s, %s)
            """, (purchase['student_id'], purchase['rp_spent'], purchase_id, f"Refund for rejected: {purchase['item_name']}"))

        conn.commit()
        flash("Purchase request rejected and RP refunded.", "warning")
    except Exception as e:
        conn.rollback()
        flash("Error rejecting purchase.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_shop_purchases'))
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
@app.route("/lms/placement-readiness")
def placement_course():
    return render_template("placement_course.html")


@app.route("/lms/deep-learning")
def deep_learning_course():
    return render_template("deep_learning_course.html")
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

    # -----------------------------------------
    # Get selected phase
    # -----------------------------------------
    selected_phase = request.args.get("phase", "phase1")

    # Only allow valid phases
    allowed_phases = {
        "phase1": "phase1_marks",
        "phase2": "phase2_marks"
    }

    # If invalid phase is supplied, default to Phase-1
    if selected_phase not in allowed_phases:
        selected_phase = "phase1"

    table_name = allowed_phases[selected_phase]

    # -----------------------------------------
    # Get selected evaluation component
    # -----------------------------------------
    selected_type = request.args.get("type")

    marks = []

    # -----------------------------------------
    # Allowed database columns
    # -----------------------------------------
    allowed_columns = {
        "class_participation": "class_participation",
        "progressive_eval": "progressive_eval",
        "internal_viva": "internal_viva",
        "mid_term_1": "mid_term_1",
        "mid_term_2": "mid_term_2"
    }

    # -----------------------------------------
    # Fetch marks
    # -----------------------------------------
    if selected_type and selected_type in allowed_columns:

        column = allowed_columns[selected_type]

        conn = get_db_connection()

        if conn is None:
            flash("Database Connection Failed!", "danger")
            return redirect(url_for("home"))

        cursor = conn.cursor()

        # Only show courses where the selected
        # evaluation component has marks uploaded.
        query = f"""
            SELECT
                course_code,
                {column} AS marks
            FROM {table_name}
            WHERE student_id = %s
              AND {column} IS NOT NULL
            ORDER BY course_code
        """

        cursor.execute(query, (student_id,))

        marks = cursor.fetchall()

        cursor.close()
        conn.close()

    # -----------------------------------------
    # Send data to template
    # -----------------------------------------
    return render_template(
        "internal_marks.html",
        marks=marks,
        selected_type=selected_type,
        selected_phase=selected_phase
    )


@app.route('/phase2')
def phase2():
    return render_template('phase2.html')

@app.route('/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- ADMIN MODULE ---

# --- ADMIN MODULE ---

from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash

@app.route('/admin', methods=['GET'])
def admin_portal():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    if conn is None:
        flash("Database Connection Failed!", "danger")
        return redirect(url_for("login"))
    
    # Use DictCursor if available so template properties (e.g. student.id, student.name) work seamlessly
    cursor = conn.cursor()
    
    try:
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

    except Exception as e:
        flash(f"An error occurred while fetching data: {str(e)}", "danger")
        students, assignments, submissions, admin_quizzes = [], [], [], []
    finally:
        cursor.close()
        conn.close()
    
    # Pass current_date explicitly to prevent Jinja evaluation issues, and pass datetime module safely
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template(
        'admin_portal.html', 
        students=students, 
        assignments=assignments, 
        submissions=submissions, 
        selected_assign_id=selected_assign_id, 
        admin_quizzes=admin_quizzes, 
        datetime=datetime,
        current_date=current_date
    )

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