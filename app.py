from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import csv
import io
from flask import Response

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'  
app.secret_key = 'your_super_secret_key_here' # Needed for session cookies and flash messages

# Configure File Uploads securely with an Absolute Path
import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Helper function to check valid image uploads
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# Ensure upload directory exists
#os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Helper function to check valid image uploads
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==========================================
# DATABASE CONNECTION
# ==========================================
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",          # Change if your XAMPP/WAMP uses a different username
        password="",          # Change if you set a MySQL password
        database="collab_growth"
    )

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================
# ==========================================
# FORGOT PASSWORD ROUTE
# ==========================================
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        new_password = request.form.get('new_password')
        
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        
        # 1. Check if the email actually exists in the database
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if user:
            # 2. Hash the new password securely
            hashed_password = generate_password_hash(new_password)
            
            # 3. Update the database
            cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_password, email))
            db.commit()
            
            flash('Password reset successfully! You can now log in.', 'success')
            cursor.close()
            db.close()
            return redirect(url_for('login'))
        else:
            flash('That email address is not registered in our system.', 'danger')
            
        cursor.close()
        db.close()
        
    return render_template('forgot_password.html')
# ==========================================
# PUBLIC BUSINESS PROFILE ROUTE
# ==========================================
@app.route('/business/<int:business_id>')
def public_business(business_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Fetch the business profile and their core user info
    cursor.execute("""
        SELECT b.*, u.name, u.email 
        FROM business_profiles b 
        JOIN users u ON b.user_id = u.id 
        WHERE u.id = %s
    """, (business_id,))
    
    business = cursor.fetchone()
    cursor.close()
    db.close()

    if not business:
        flash("This business has not set up their public profile yet.", "info")
        return redirect(url_for('dashboard'))

    return render_template('public_business.html', business=business)
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        hashed_password = generate_password_hash(password)
        db = get_db_connection()
        cursor = db.cursor()

        try:
            cursor.execute("INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)", 
                           (name, email, hashed_password, role))
            db.commit()
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            flash("Email already exists or database error occurred.", "red")
        finally:
            cursor.close()
            db.close()

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Safely fetch form data using .get() to prevent KeyErrors
        email = request.form.get('email')
        password = request.form.get('password')

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user and check_password_hash(user['password'], password):
            # Create session
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            session['email'] = user['email']

            # SMART ROUTING: Send Admins to the command center, everyone else to the dashboard
            if session['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            # Safely returning the error variable exactly as your HTML expects it
            return render_template('login.html', error="Invalid email or password.")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been securely logged out.", "success")
    return redirect(url_for('login'))

# ==========================================
# DASHBOARD ROUTE
# ==========================================
@app.route('/dashboard')
def dashboard():
    # Security Check
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    role = session['role']
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Set default empty lists so the HTML doesn't crash if they are empty
    inquiries = []
    saved_creators = [] 

    # --- IF LOGGED IN AS A CREATOR ---
    if role == 'creator':
        cursor.execute("""
            SELECT m.sender_id, m.content, m.timestamp, u.name AS sender_name, u.email AS sender_email 
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.receiver_id = %s
            ORDER BY m.timestamp DESC
        """, (user_id,))
        inquiries = cursor.fetchall()

    # --- IF LOGGED IN AS A BUSINESS ---
    elif role == 'business':
        # 1. Fetch the Saved Creators (Bulletproof query with fallbacks)
        cursor.execute("""
            SELECT 
                u.id AS user_id, 
                u.name, 
                IFNULL(cp.profile_pic, 'default.png') AS profile_pic, 
                IFNULL(cp.niche, 'Content Creator') AS niche 
            FROM saved_creators sc
            JOIN users u ON sc.creator_id = u.id
            LEFT JOIN creator_profiles cp ON u.id = cp.user_id
            WHERE sc.business_id = %s
        """, (user_id,))
        saved_creators = cursor.fetchall()

        # 2. Fetch replies/messages sent TO the business
        cursor.execute("""
            SELECT m.sender_id, m.content, m.timestamp, u.name AS sender_name, u.email AS sender_email 
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.receiver_id = %s
            ORDER BY m.timestamp DESC
        """, (user_id,))
        inquiries = cursor.fetchall()

    cursor.close()
    db.close()

    # THE CRITICAL LINE: Passing 'saved_creators' to the HTML!
    return render_template('dashboard.html', role=role, inquiries=inquiries, saved_creators=saved_creators)
# ==========================================
# EDIT PROFILE ROUTE
# ==========================================
@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    # 1. Security Check: Only logged-in creators can access this page
    if 'user_id' not in session or session.get('role') != 'creator':
        flash('Please log in as a creator to access this page.', 'danger')
        return redirect(url_for('login'))

    user_id = session['user_id']
    
    # USE YOUR APP'S CUSTOM DB CONNECTION FUNCTION HERE!
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # 2. Handle Form Submission (POST Request)
    if request.method == 'POST':
        niche = request.form.get('niche')
        location = request.form.get('location')
        base_price = request.form.get('base_price')
        bio = request.form.get('bio')
        instagram_link = request.form.get('instagram_link')
        portfolio_link = request.form.get('portfolio_link')

        # Handle Profile Picture Upload
        profile_pic_name = None
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_pic_name = filename

        # Update the database
        if profile_pic_name:
            cursor.execute('''
                UPDATE creator_profiles 
                SET niche=%s, location=%s, base_price=%s, bio=%s, instagram_link=%s, portfolio_link=%s, profile_pic=%s 
                WHERE user_id=%s
            ''', (niche, location, base_price, bio, instagram_link, portfolio_link, profile_pic_name, user_id))
        else:
            cursor.execute('''
                UPDATE creator_profiles 
                SET niche=%s, location=%s, base_price=%s, bio=%s, instagram_link=%s, portfolio_link=%s 
                WHERE user_id=%s
            ''', (niche, location, base_price, bio, instagram_link, portfolio_link, user_id))
        
        db.commit() # Changed from mysql.connection.commit()
        cursor.close()
        db.close()  # Good practice to close the connection
        
        flash('Your portfolio has been updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    # 3. Handle Page Load (GET Request)
    cursor.execute("SELECT * FROM creator_profiles WHERE user_id = %s", (user_id,))
    creator = cursor.fetchone()
    cursor.close()
    db.close()

    if not creator:
        creator = {}

    return render_template('edit_profile.html', creator=creator)
# ==========================================
# PROFILE SETUP ROUTES
# ==========================================
@app.route('/profile', methods=['GET', 'POST'])
def profile_setup():
    if 'user_id' not in session or session['role'] != 'creator':
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        niche = request.form['niche']
        location = request.form['location']
        base_price = request.form['base_price']
        instagram_link = request.form['instagram_link']
        portfolio_link = request.form['portfolio_link']
        bio = request.form['bio']
        
        # Handle Profile Picture Upload
        filename = "default.png" # Default image
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and allowed_file(file.filename):
                # Create a secure, unique filename using the user's ID
                filename = f"user_{session['user_id']}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # Check if profile already exists to update instead of insert
        cursor.execute("SELECT * FROM creator_profiles WHERE user_id = %s", (session['user_id'],))
        existing_profile = cursor.fetchone()

        if existing_profile:
            # If they didn't upload a new pic, keep the old one
            if filename == "default.png":
                filename = existing_profile['profile_pic']
                
            cursor.execute("""
                UPDATE creator_profiles 
                SET profile_pic=%s, niche=%s, location=%s, base_price=%s, instagram_link=%s, portfolio_link=%s, bio=%s 
                WHERE user_id=%s
            """, (filename, niche, location, base_price, instagram_link, portfolio_link, bio, session['user_id']))
        else:
            cursor.execute("""
                INSERT INTO creator_profiles (user_id, profile_pic, niche, location, base_price, instagram_link, portfolio_link, bio) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (session['user_id'], filename, niche, location, base_price, instagram_link, portfolio_link, bio))

        db.commit()
        cursor.close()
        db.close()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('dashboard'))

    # GET request: pre-fill form if data exists
    cursor.execute("SELECT * FROM creator_profiles WHERE user_id = %s", (session['user_id'],))
    profile = cursor.fetchone()
    cursor.close()
    db.close()
    
    return render_template('profile_setup.html', profile=profile)

@app.route('/business_profile', methods=['GET', 'POST'])
def business_setup():
    if 'user_id' not in session or session['role'] != 'business':
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        company_name = request.form['company_name']
        industry = request.form['industry']
        website_link = request.form['website_link']
        description = request.form['description']

        cursor.execute("SELECT * FROM business_profiles WHERE user_id = %s", (session['user_id'],))
        if cursor.fetchone():
            cursor.execute("""
                UPDATE business_profiles 
                SET company_name=%s, industry=%s, website_link=%s, description=%s 
                WHERE user_id=%s
            """, (company_name, industry, website_link, description, session['user_id']))
        else:
            cursor.execute("""
                INSERT INTO business_profiles (user_id, company_name, industry, website_link, description) 
                VALUES (%s, %s, %s, %s, %s)
            """, (session['user_id'], company_name, industry, website_link, description))

        db.commit()
        cursor.close()
        db.close()
        flash("Business profile saved successfully!", "success")
        return redirect(url_for('dashboard'))

    cursor.execute("SELECT * FROM business_profiles WHERE user_id = %s", (session['user_id'],))
    profile = cursor.fetchone()
    cursor.close()
    db.close()

    return render_template('business_setup.html', profile=profile)


# ==========================================
# SEARCH & EXPLORE ROUTES
# ==========================================
@app.route('/search')
def search():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    query = request.args.get('query', '')
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if query:
        # Search by Niche, Location, or Name
        search_term = f"%{query}%"
        cursor.execute("""
            SELECT c.*, u.name 
            FROM creator_profiles c 
            JOIN users u ON c.user_id = u.id 
            WHERE c.niche LIKE %s OR c.location LIKE %s OR u.name LIKE %s
        """, (search_term, search_term, search_term))
    else:
        # Show all creators if no search query
        cursor.execute("""
            SELECT c.*, u.name 
            FROM creator_profiles c 
            JOIN users u ON c.user_id = u.id
        """)
        
    creators = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('search.html', creators=creators, query=query)

@app.route('/creator/<int:creator_id>')
def public_profile(creator_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT c.*, u.name, u.email 
        FROM creator_profiles c 
        JOIN users u ON c.user_id = u.id 
        WHERE u.id = %s
    """, (creator_id,))
    
    creator = cursor.fetchone()
    cursor.close()
    db.close()

    if not creator:
        flash("Creator profile not found.", "red")
        return redirect(url_for('search'))

    return render_template('public_profile.html', creator=creator)


@app.route('/edit_business_profile', methods=['GET', 'POST'])
def edit_business_profile():
    # Make sure user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        new_name = request.form.get('name')
        new_email = request.form.get('email')
        
        # Grab the new fields from the form
        company_type = request.form.get('company_type')
        working_hours = request.form.get('working_hours')
        location = request.form.get('location')

        # Update the database with all 5 fields
        cursor.execute("""
            UPDATE users 
            SET name = %s, email = %s, company_type = %s, working_hours = %s, location = %s 
            WHERE id = %s
        """, (new_name, new_email, company_type, working_hours, location, user_id))
        
        db.commit()
        flash("Business profile updated successfully!", "success")
        return redirect(url_for('dashboard'))

    # Fetch current data (including new fields) to pre-fill the form
    cursor.execute("""
        SELECT name, email, company_type, working_hours, location 
        FROM users WHERE id = %s
    """, (user_id,))
    
    business_data = cursor.fetchone()
    cursor.close()
    db.close()

    return render_template('edit_business_profile.html', business=business_data)

@app.route('/business/<int:business_id>')
def view_business(business_id):
    # Make sure the user is logged in (so only registered creators can see it)
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Fetch the business details using the ID from the URL
    cursor.execute("""
        SELECT name, email, company_type, working_hours, location 
        FROM users 
        WHERE id = %s AND role = 'business'
    """, (business_id,))
    
    business_data = cursor.fetchone()
    cursor.close()
    db.close()

    # If someone tries to view a business that doesn't exist
    if not business_data:
        return "Business not found", 404

    return render_template('view_business.html', business=business_data)
# ==========================================
# INTERACTION ROUTES (SAVE & MESSAGE)
# ==========================================
@app.route('/save_creator/<int:creator_id>')
def save_creator(creator_id):
    # Only businesses can save creators
    if 'user_id' not in session or session.get('role') != 'business':
        return redirect(url_for('login'))
        
    business_id = session['user_id']
    db = get_db_connection()
    cursor = db.cursor()
    
    # Check if this creator is already saved to prevent duplicates
    cursor.execute("SELECT * FROM saved_creators WHERE business_id = %s AND creator_id = %s", (business_id, creator_id))
    already_saved = cursor.fetchone()
    
    if not already_saved:
        # If not saved yet, insert them into the database!
        cursor.execute("INSERT INTO saved_creators (business_id, creator_id) VALUES (%s, %s)", (business_id, creator_id))
        db.commit()
        flash("Creator saved to your roster!", "success")
    else:
        flash("This creator is already in your roster.", "info")
        
    cursor.close()
    db.close()
    
    # Send the user back to the dashboard to see their updated roster
    return redirect(url_for('dashboard'))

@app.route('/send_message/<int:creator_id>', methods=['POST'])
def send_message(creator_id):
    if 'user_id' not in session or session['role'] != 'business':
        return redirect(url_for('login'))

    message_content = request.form['message']
    
    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute("INSERT INTO messages (sender_id, receiver_id, message) VALUES (%s, %s, %s)", 
                       (session['user_id'], creator_id, message_content))
        db.commit()
        flash("Your inquiry has been sent successfully!", "success")
    except Exception as e:
        flash("Failed to send message. Please try again.", "red")
    finally:
        cursor.close()
        db.close()

    return redirect(url_for('public_profile', creator_id=creator_id))

# ==========================================
# TWO-WAY CHAT ROOM ROUTE
# ==========================================
@app.route('/chat/<int:other_user_id>', methods=['GET', 'POST'])
def chat(other_user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    my_id = session['user_id']
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Get the name of the person we are chatting with
    cursor.execute("SELECT name FROM users WHERE id = %s", (other_user_id,))
    other_user = cursor.fetchone()
    
    if not other_user:
        return "User not found", 404
        
    # If the user types a message and hits send
    if request.method == 'POST':
        content = request.form.get('content')
        if content:
            cursor.execute("""
                INSERT INTO messages (sender_id, receiver_id, content) 
                VALUES (%s, %s, %s)
            """, (my_id, other_user_id, content))
            db.commit()
            return redirect(url_for('chat', other_user_id=other_user_id))
            
    # Fetch the entire conversation history between these two users
    cursor.execute("""
        SELECT sender_id, content, timestamp 
        FROM messages 
        WHERE (sender_id = %s AND receiver_id = %s) 
           OR (sender_id = %s AND receiver_id = %s)
        ORDER BY timestamp ASC
    """, (my_id, other_user_id, other_user_id, my_id))
    
    chat_history = cursor.fetchall()
    cursor.close()
    db.close()
    
    return render_template('chat.html', chat_history=chat_history, other_user=other_user, my_id=my_id)

@app.route('/unsave/<int:creator_id>')
def unsave_creator(creator_id):
    # Security check: only logged-in businesses can unsave
    if 'user_id' not in session or session.get('role') != 'business':
        return redirect(url_for('login'))
        
    business_id = session['user_id']
    db = get_db_connection()
    cursor = db.cursor()
    
    # Delete the connection from the saved_creators table
    cursor.execute("""
        DELETE FROM saved_creators 
        WHERE business_id = %s AND creator_id = %s
    """, (business_id, creator_id))
    
    db.commit()
    cursor.close()
    db.close()
    
    flash("Creator removed from your roster.", "success")
    return redirect(url_for('dashboard'))

# ==========================================
# ADMIN PANEL ROUTES
# ==========================================

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # 1. Existing Stats
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'creator'")
    total_creators = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'business'")
    total_businesses = cursor.fetchone()['count']

    # 2. NEW: Total Interactions (Total Messages Sent)
    cursor.execute("SELECT COUNT(*) as count FROM messages")
    total_interactions = cursor.fetchone()['count']

    # 3. NEW: Interaction Logs (Who is talking to whom)
    cursor.execute("""
        SELECT 
            m.timestamp, 
            u1.name AS sender_name, 
            u2.name AS receiver_name, 
            m.content 
        FROM messages m
        JOIN users u1 ON m.sender_id = u1.id
        JOIN users u2 ON m.receiver_id = u2.id
        ORDER BY m.timestamp DESC 
        LIMIT 10
    """)
    recent_chats = cursor.fetchall()

    # 4. Master User List
    cursor.execute("SELECT id, name, email, role FROM users ORDER BY id DESC")
    all_users = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template('admin_dashboard.html', 
                           total_creators=total_creators, 
                           total_businesses=total_businesses, 
                           total_interactions=total_interactions,
                           recent_chats=recent_chats,
                           all_users=all_users,
                           total_users=(total_creators + total_businesses))

@app.route('/admin/delete_user/<int:user_id>')
def delete_user(user_id):
    # SECURITY CHECK
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor()

    try:
        # To delete a user, we must first delete everything attached to them 
        # (Messages, Saved Lists, and Profiles) so MySQL doesn't block it!
        cursor.execute("DELETE FROM messages WHERE sender_id = %s OR receiver_id = %s", (user_id, user_id))
        cursor.execute("DELETE FROM saved_creators WHERE business_id = %s OR creator_id = %s", (user_id, user_id))
        cursor.execute("DELETE FROM creator_profiles WHERE user_id = %s", (user_id,))
        
        # Finally, delete the actual user account
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()
        flash("User and all associated data permanently deleted.", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error deleting user: {str(e)}", "danger")
    finally:
        cursor.close()
        db.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_role', methods=['POST'])
def admin_update_role():
    # Security check
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    user_id = request.form.get('user_id')
    new_role = request.form.get('new_role')
    
    # Ensure they only submit valid roles
    if new_role not in ['admin', 'creator', 'business']:
        flash("Invalid role selected.", "danger")
        return redirect(url_for('admin_dashboard'))

    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
    db.commit()
    cursor.close()
    db.close()
    
    flash(f"User #{user_id} role successfully updated to {new_role}.", "success")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/reset_password', methods=['POST'])
def admin_reset_password():
    # Security check
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    user_id = request.form.get('user_id')
    new_password = request.form.get('new_password')
    
    # Encrypt the new password before saving it
    hashed_pw = generate_password_hash(new_password)
    
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_pw, user_id))
    db.commit()
    cursor.close()
    db.close()
    
    flash(f"Password for user #{user_id} has been securely reset.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/setup_admin')
def setup_admin():
    db = get_db_connection()
    cursor = db.cursor()

    # Check if an admin already exists to prevent duplicates
    cursor.execute("SELECT * FROM users WHERE role = 'admin'")
    admin_exists = cursor.fetchone()

    if not admin_exists:
        # Generate a secure password for the default admin
        hashed_pw = generate_password_hash('admin123')
        
        # Insert the master admin account
        cursor.execute("""
            INSERT INTO users (name, email, password, role) 
            VALUES (%s, %s, %s, %s)
        """, ('System Administrator', 'admin@collabgrowth.com', hashed_pw, 'admin'))
        
        db.commit()
        flash("Master Admin account created! You can now log in.", "success")
    else:
        flash("Admin account already exists in the system.", "info")

    cursor.close()
    db.close()
    
    # Send them to the login page to try it out
    return redirect(url_for('login'))

@app.route('/admin/export_users')
def export_users():
    # Security check
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Fetch all user data
    cursor.execute("SELECT id, name, email, role FROM users ORDER BY id ASC")
    users = cursor.fetchall()
    
    # Create a string buffer to write CSV data
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write the Header Row
    writer.writerow(['User ID', 'Full Name', 'Email Address', 'Account Role'])
    
    # Write User Data Rows
    for user in users:
        writer.writerow([user['id'], user['name'], user['email'], user['role']])
    
    cursor.close()
    db.close()

    # Create the response as a downloadable file
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=collab_growth_users.csv'
    return response
if __name__ == '__main__':
    app.run(debug=True)