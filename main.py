from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import os
from datetime import datetime
import openai
import json
from dotenv import load_dotenv
from models import db, User, Goal, Workout, Exercise, Progress, Streak, Message, MoodEntry, JournalEntry, MeditationSession
from functools import wraps
from responses import (
    get_workout_response,
    get_nutrition_response,
    get_motivation_response,
    get_recovery_response,
    get_progress_response,
    get_technique_response
)

load_dotenv()

# Configure OpenAI API
openai.api_key = os.getenv('OPENAI_API_KEY')
if not openai.api_key:
    print("Warning: OPENAI_API_KEY not found in environment variables")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-very-secret-key')
# Use absolute path for database
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plan_a.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def create_admin_user():
    admin = User.query.filter_by(email='admin@aurafit.com').first()
    if not admin:
        admin = User(
            email='admin@aurafit.com',
            name='Admin',
            is_admin=True,
            onboarding_complete=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

# Create admin user when app starts
with app.app_context():
    db.create_all()
    create_admin_user()

# Routes
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_messages'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            if user.is_admin:
                return redirect(url_for('admin_messages'))
            if not user.onboarding_complete:
                return redirect(url_for('onboarding'))
            return redirect(url_for('dashboard'))
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        name = request.form.get('name', '')
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))
        user = User(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user, remember=True)
        return redirect(url_for('onboarding'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/onboarding', methods=['GET', 'POST'])
@login_required
def onboarding():
    user = current_user
    if request.method == 'POST':
        step = int(request.form.get('step', 1))
        if step == 1:
            user.name = request.form['name']
            user.age = int(request.form['age'])
            user.gender = request.form['gender']
        elif step == 2:
            user.height = float(request.form['height'])
            user.weight = float(request.form['weight'])
        elif step == 3:
            user.fitness_goal = request.form['fitness_goal']
        elif step == 4:
            user.activity_level = request.form['activity_level']
            user.onboarding_complete = True
        db.session.commit()
        if step < 4:
            return redirect(url_for('onboarding', step=step+1))
        return redirect(url_for('dashboard'))
    step = int(request.args.get('step', 1))
    return render_template('onboarding.html', step=step, user=user)

@app.route('/chatbot')
@login_required
def chatbot():
    # Example messages for demonstration
    messages = [
        {'message': 'Hello! I am your AI fitness coach.', 'is_bot': True, 'timestamp': datetime.now(), 'style': 'background: #f1f1f1; color: #333;'},
        {'message': 'Show me a workout!', 'is_bot': False, 'timestamp': datetime.now(), 'style': 'background: #3498db; color: white; margin-left: auto;'},
    ]
    return render_template('chatbot.html', now=datetime.now, messages=messages)

@app.route('/progress')
@login_required
def progress():
    return render_template('progress.html')

@app.route('/streaks')
@login_required
def streaks():
    return render_template('streaks.html')

@app.route('/goals')
@login_required
def goals():
    user_goals = Goal.query.filter_by(user_id=current_user.id).all()
    return render_template('goals.html', goals=user_goals)

@app.route('/add_goal', methods=['POST'])
@login_required
def add_goal():
    try:
        category = request.form.get('goal_category')
        title = request.form.get('goal_title')
        deadline_str = request.form.get('goal_deadline')
        deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
        print(f"Received goal data: category={category}, title={title}, deadline={deadline}")
        new_goal = Goal(
            user_id=current_user.id,
            category=category,
            title=title,
            deadline=deadline
        )
        db.session.add(new_goal)
        db.session.commit()
        print(f"Goal added successfully: {new_goal.id}")
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error adding goal: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/update_goal_progress/<int:goal_id>', methods=['POST'])
def update_goal_progress(goal_id):
    data = request.get_json()
    progress = int(data.get('progress', 0))
    
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first()
    if goal:
        goal.progress = progress
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Goal not found'})

@app.route('/delete_goal/<int:goal_id>', methods=['POST'])
def delete_goal(goal_id):
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first()
    if goal:
        db.session.delete(goal)
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Goal not found'})

@app.route('/workouts')
@login_required
def workouts():
    user = current_user
    personalized_workouts = Workout.query.filter_by(user_id=user.id).all()
    return render_template('workouts.html', workouts=personalized_workouts, predefined_workouts=[])

@app.route('/workouts/add', methods=['POST'])
@login_required
def add_workout():
    data = request.get_json()
    workout = Workout(
        name=data['name'],
        description=data['description'],
        type=data['type'],
        difficulty=data['difficulty'],
        duration=data['duration'],
        calories_burned=data['calories_burned'],
        user_id=current_user.id
    )
    db.session.add(workout)
    db.session.commit()
    for exercise_data in data['exercises']:
        exercise = Exercise(
            name=exercise_data['name'],
            sets=exercise_data['sets'],
            reps=exercise_data['reps'],
            workout_id=workout.id
        )
        db.session.add(exercise)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/workouts/<int:workout_id>/delete', methods=['POST'])
@login_required
def delete_workout(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    db.session.delete(workout)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/workouts/suggest', methods=['POST'])
@login_required
def suggest_workout():
    user = current_user
    prompt = f"""
    Create a personalized workout plan for a {user.age}-year-old {user.gender} with the following details:
    - Height: {user.height} cm
    - Weight: {user.weight} kg
    - Fitness Goal: {user.fitness_goal}
    - Activity Level: {user.activity_level}
    Please suggest a workout that includes:
    1. A name and description
    2. The type of workout (cardio, strength, or flexibility)
    3. The difficulty level (beginner, intermediate, or advanced)
    4. The estimated duration in minutes
    5. The estimated calories burned
    6. A list of 3-5 exercises with sets and reps (or duration for cardio)
    Format the response as a JSON object with the following structure:
    {{
        "name": "workout name",
        "description": "workout description",
        "type": "workout type",
        "difficulty": "difficulty level",
        "duration": duration_in_minutes,
        "calories_burned": estimated_calories,
        "exercises": [
            {{
                "name": "exercise name",
                "sets": number_of_sets,
                "reps": number_of_reps
            }},
            ...
        ]
    }}
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a fitness expert creating personalized workout plans."},
                {"role": "user", "content": prompt}
            ]
        )
        workout_data = response.choices[0].message.content
        return jsonify({'success': True, 'workout': workout_data})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/workouts/<int:workout_id>/start', methods=['POST'])
@login_required
def start_workout(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    if workout.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    # Create a new progress entry
    progress = Progress(
        user_id=current_user.id,
        workout_id=workout_id,
        start_time=datetime.now(),
        status='in_progress'
    )
    db.session.add(progress)
    db.session.commit()
    return jsonify({'success': True, 'progress_id': progress.id})

@app.route('/workouts/<int:workout_id>/complete', methods=['POST'])
@login_required
def complete_workout(workout_id):
    data = request.get_json()
    progress_id = data.get('progress_id')
    
    progress = Progress.query.get_or_404(progress_id)
    if progress.user_id != current_user.id or progress.workout_id != workout_id:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    
    progress.end_time = datetime.now()
    progress.status = 'completed'
    progress.notes = data.get('notes', '')
    
    # Update streak
    streak = Streak.query.filter_by(user_id=current_user.id).first()
    if not streak:
        streak = Streak(user_id=current_user.id, current_streak=1, longest_streak=1)
        db.session.add(streak)
    else:
        streak.current_streak += 1
        if streak.current_streak > streak.longest_streak:
            streak.longest_streak = streak.current_streak
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/progress/update', methods=['POST'])
@login_required
def update_progress():
    data = request.get_json()
    weight = data.get('weight')
    measurements = data.get('measurements', {})
    
    progress = Progress(
        user_id=current_user.id,
        weight=weight,
        measurements=json.dumps(measurements),
        date=datetime.now()
    )
    db.session.add(progress)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        user = current_user
        user.name = request.form.get('name', user.name)
        user.age = int(request.form.get('age', user.age))
        user.gender = request.form.get('gender', user.gender)
        user.height = float(request.form.get('height', user.height))
        user.weight = float(request.form.get('weight', user.weight))
        user.fitness_goal = request.form.get('fitness_goal', user.fitness_goal)
        user.activity_level = request.form.get('activity_level', user.activity_level)
        db.session.commit()
        flash('Profile updated successfully!')
        return redirect(url_for('profile'))
    return render_template('profile.html', user=current_user)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')
        
        new_message = Message(
            name=name,
            email=email,
            subject=subject,
            message=message
        )
        
        db.session.add(new_message)
        db.session.commit()
        
        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

@app.route('/admin/messages')
@login_required
@admin_required
def admin_messages():
    messages = Message.query.order_by(Message.created_at.desc()).all()
    return render_template('admin/messages.html', messages=messages)

@app.route('/admin/messages/<int:message_id>')
@login_required
@admin_required
def admin_view_message(message_id):
    message = Message.query.get_or_404(message_id)
    message.is_read = True
    db.session.commit()
    return render_template('admin/view_message.html', message=message)

@app.route('/admin/messages/<int:message_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_message(message_id):
    message = Message.query.get_or_404(message_id)
    db.session.delete(message)
    db.session.commit()
    flash('Message deleted successfully.', 'success')
    return redirect(url_for('admin_messages'))

@app.route('/workouts/level/<level>')
@login_required
def get_level_exercises(level):
    # Example: Personalize based on user preferences
    user = current_user
    # You can expand this logic for real personalization
    base_exercises = {
        'beginner': [
            {'name': 'Jumping Jacks', 'duration': 30, 'gif': '/static/exercises/jumping_jacks.gif'},
            {'name': 'Bodyweight Squats', 'reps': 12, 'gif': '/static/exercises/bodyweight_squats.gif'},
            {'name': 'Push-ups', 'reps': 8, 'gif': '/static/exercises/push_ups.gif'},
            {'name': 'Plank', 'duration': 30, 'gif': '/static/exercises/plank.gif'},
            {'name': 'High Knees', 'duration': 30, 'gif': '/static/exercises/high_knees.gif'},
            {'name': 'Standing Toe Touch', 'reps': 10, 'gif': '/static/exercises/standing_toe_touch.gif'},
        ],
        'intermediate': [
            {'name': 'Burpees', 'reps': 10, 'gif': '/static/exercises/burpees.gif'},
            {'name': 'Lunges', 'reps': 12, 'gif': '/static/exercises/lunges.gif'},
            {'name': 'Mountain Climbers', 'duration': 40, 'gif': '/static/exercises/mountain_climbers.gif'},
            {'name': 'Tricep Dips', 'reps': 10, 'gif': '/static/exercises/tricep_dips.gif'},
            {'name': 'Jump Squats', 'reps': 12, 'gif': '/static/exercises/jump_squats.gif'},
            {'name': 'Russian Twists', 'reps': 20, 'gif': '/static/exercises/russian_twists.gif'},
        ],
        'advanced': [
            {'name': 'Pistol Squats', 'reps': 8, 'gif': '/static/exercises/pistol_squat.gif'},
            {'name': 'Pull-ups', 'reps': 8, 'gif': '/static/exercises/pull_up.gif'},
            {'name': 'Handstand Push-ups', 'reps': 6, 'gif': '/static/exercises/handstand-push-up.gif'},
            {'name': 'Plank to Push-up', 'duration': 45, 'gif': '/static/exercises/plank_to_pushup.gif'},
            {'name': 'Jump Lunges', 'reps': 12, 'gif': '/static/exercises/jump_lunges.gif'},
            {'name': 'V-Ups', 'reps': 15, 'gif': '/static/exercises/v_ups.gif'},
        ]
    }
    # Example: Adjust for user goal
    exercises = base_exercises.get(level, [])
    if user.fitness_goal == 'weight_loss':
        exercises.append({'name': 'High Knees', 'duration': 30, 'gif': '/static/exercises/high_knees.gif'})
    elif user.fitness_goal == 'muscle_gain':
        exercises.append({'name': 'Weighted Squats', 'reps': 10, 'gif': '/static/exercises/weighted_squats.gif'})
    return jsonify({'exercises': exercises})

@app.route('/mental-health')
@login_required
def mental_health():
    return render_template('mental_health.html')

@app.route('/save-mood', methods=['POST'])
@login_required
def save_mood():
    data = request.get_json()
    mood = data.get('mood')
    
    if not mood:
        return jsonify({'error': 'Mood is required'}), 400
        
    mood_entry = MoodEntry(user_id=current_user.id, mood=mood)
    db.session.add(mood_entry)
    db.session.commit()
    
    return jsonify({'message': 'Mood saved successfully'})

@app.route('/save-journal', methods=['POST'])
@login_required
def save_journal():
    data = request.get_json()
    entry = data.get('entry')
    
    if not entry:
        return jsonify({'error': 'Journal entry is required'}), 400
        
    journal_entry = JournalEntry(user_id=current_user.id, content=entry)
    db.session.add(journal_entry)
    db.session.commit()
    
    return jsonify({'message': 'Journal entry saved successfully'})

@app.route('/save-meditation', methods=['POST'])
@login_required
def save_meditation():
    data = request.get_json()
    duration = data.get('duration')
    
    if not duration:
        return jsonify({'error': 'Duration is required'}), 400
        
    meditation_session = MeditationSession(user_id=current_user.id, duration=duration)
    db.session.add(meditation_session)
    db.session.commit()
    
    return jsonify({'message': 'Meditation session saved successfully'})

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json()
    user_message = data.get('message', '').lower()
    
    if not user_message:
        return jsonify({
            'success': False,
            'error': 'Message cannot be empty'
        }), 400
    
    # Get user's fitness profile
    user = current_user
    
    # Determine user's fitness level based on activity_level
    fitness_level = 'beginner'
    if user.activity_level == 'moderate':
        fitness_level = 'intermediate'
    elif user.activity_level == 'very_active':
        fitness_level = 'advanced'
    
    # Extract keywords from user message
    keywords = user_message.split()
    
    # Generate response based on message content
    if any(word in user_message for word in ['workout', 'exercise', 'training', 'routine']):
        response = get_workout_response(fitness_level, keywords)
    elif any(word in user_message for word in ['diet', 'nutrition', 'food', 'eat', 'meal']):
        response = get_nutrition_response(user.fitness_goal, keywords)
    elif any(word in user_message for word in ['motivation', 'motivated', 'tired', 'hard', 'difficult']):
        response = get_motivation_response(keywords)
    elif any(word in user_message for word in ['recovery', 'rest', 'sleep', 'rest day']):
        response = get_recovery_response(keywords)
    elif any(word in user_message for word in ['progress', 'track', 'measure', 'goal']):
        response = get_progress_response(keywords)
    elif any(word in user_message for word in ['form', 'technique', 'proper', 'correct']):
        response = get_technique_response(keywords)
    elif 'log my workout' in user_message:
        # Handle workout logging
        try:
            # Create a new workout entry
            workout = Workout(
                user_id=user.id,
                name=f"Workout on {datetime.now().strftime('%Y-%m-%d')}",
                type='general',
                duration=30,  # Default duration
                difficulty=fitness_level,
                calories_burned=0
            )
            db.session.add(workout)
            
            # Add some default exercises
            exercises = [
                ('Bodyweight Squats', 3, 12),
                ('Push-ups', 3, 10),
                ('Lunges', 3, 10),
                ('Plank', 3, 30)  # 30 seconds
            ]
            
            for name, sets, reps in exercises:
                ex = Exercise(
                    name=name,
                    sets=sets,
                    reps=reps,
                    workout_id=workout.id
                )
                db.session.add(ex)
            
            db.session.commit()
            response = "I've logged a basic workout for you! You can view and modify it in your workout history."
        except Exception as e:
            print(f"Error logging workout: {str(e)}")
            response = "I couldn't log your workout automatically. Please try logging it manually in the Workouts section."
    else:
        response = "I'm here to help with your fitness journey! You can ask me about workouts, nutrition, motivation, recovery, progress tracking, or proper form. What would you like to know?"
    
    return jsonify({
        'success': True,
        'response': response
    })

if __name__ == '__main__':
    app.run(debug=True) 