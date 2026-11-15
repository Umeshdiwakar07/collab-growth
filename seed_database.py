import mysql.connector
from werkzeug.security import generate_password_hash

# Connect to the database
db = mysql.connector.connect(
    host="localhost",
    user="root",      
    password="",      
    database="collab_growth"
)
cursor = db.cursor()

# Our list of fake creators
dummy_creators = [
    {
        "name": "Rahul Desai", "email": "rahul@test.com", "password": "password123",
        "niche": "Photography", "location": "Nashik", "base_price": 4000,
        "bio": "Passionate about capturing authentic moments. Specializing in portrait and event photography."
    },
    {
        "name": "Sneha Patil", "email": "sneha@test.com", "password": "password123",
        "niche": "Video Editing", "location": "Pune", "base_price": 8000,
        "bio": "Expert in Premiere Pro and DaVinci Resolve. I bring your stories to life with dynamic, fast-paced edits."
    },
    {
        "name": "Amit Joshi", "email": "amit@test.com", "password": "password123",
        "niche": "Content Writing", "location": "Mumbai", "base_price": 3000,
        "bio": "Specializing in self-development blogs, character analysis, and historical articles focusing on Maratha history."
    },
    {
        "name": "Priya Sharma", "email": "priya@test.com", "password": "password123",
        "niche": "Social Media Management", "location": "Nashik", "base_price": 10000,
        "bio": "Helping local businesses grow their online presence with engaging content and strategic scheduling."
    }
]

print("Starting to add dummy data...")

for creator in dummy_creators:
    # 1. Check if email already exists so we don't crash if you run this twice
    cursor.execute("SELECT id FROM users WHERE email = %s", (creator['email'],))
    if cursor.fetchone():
        print(f"Skipping {creator['name']} - email already exists.")
        continue

    # 2. Hash the password and insert into 'users' table
    hashed_password = generate_password_hash(creator['password'])
    user_sql = "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, 'creator')"
    cursor.execute(user_sql, (creator['name'], creator['email'], hashed_password))
    
    # Get the ID of the user we just created
    new_user_id = cursor.lastrowid

    # 3. Insert their details into 'creator_profiles' table
    profile_sql = "INSERT INTO creator_profiles (user_id, niche, location, base_price, bio) VALUES (%s, %s, %s, %s, %s)"
    profile_values = (new_user_id, creator['niche'], creator['location'], creator['base_price'], creator['bio'])
    cursor.execute(profile_sql, profile_values)
    
    print(f"Successfully added {creator['name']}!")

# Save changes and close
db.commit()
cursor.close()
db.close()

print("Database seeding complete! Your search engine is now populated.")