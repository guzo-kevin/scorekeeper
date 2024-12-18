from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from enum import Enum
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///badminton.db'
app.config['SECRET_KEY'] = 'your-secret-key'
db = SQLAlchemy(app)

class Sex(Enum):
    M = 'M'
    F = 'F'
    U = 'U'

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    sex = db.Column(db.Enum(Sex), nullable=False, default=Sex.U)
    join_date = db.Column(db.DateTime, default=datetime.utcnow)

class Pair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Define relationships
    player1 = db.relationship('Player', foreign_keys=[player1_id])
    player2 = db.relationship('Player', foreign_keys=[player2_id])

    # Add unique constraint to prevent duplicate pairs
    __table_args__ = (
        db.UniqueConstraint('player1_id', 'player2_id', name='unique_pair'),
    )

    @staticmethod
    def create_pair(player1_id, player2_id):
        # Get players
        player1 = Player.query.get(player1_id)
        player2 = Player.query.get(player2_id)
        
        if not player1 or not player2:
            raise ValueError("Both players must exist")
        
        if player1_id == player2_id:
            raise ValueError("Cannot create pair with same player")
            
        # Order players alphabetically
        if player1.name > player2.name:
            player1_id, player2_id = player2_id, player1_id
            
        # Check if pair already exists
        existing_pair = Pair.query.filter(
            and_(
                Pair.player1_id == player1_id,
                Pair.player2_id == player2_id
            )
        ).first()
        
        if existing_pair:
            raise ValueError("This pair already exists")
            
        return Pair(player1_id=player1_id, player2_id=player2_id)

class SingleMatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    player1_score = db.Column(db.Integer, nullable=False)
    player2_score = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    match_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Define relationships
    player1 = db.relationship('Player', foreign_keys=[player1_id])
    player2 = db.relationship('Player', foreign_keys=[player2_id])
    winner = db.relationship('Player', foreign_keys=[winner_id])

    @staticmethod
    def create_match(player1_id, player2_id, player1_score, player2_score):
        # Verify players exist
        player1 = Player.query.get(player1_id)
        player2 = Player.query.get(player2_id)
        
        if not player1 or not player2:
            raise ValueError("Both players must exist")
        
        if player1_id == player2_id:
            raise ValueError("Cannot record match with same player")
            
        # Ensure player1_id is the smaller ID
        if player1_id > player2_id:
            # Swap player IDs and scores
            player1_id, player2_id = player2_id, player1_id
            player1_score, player2_score = player2_score, player1_score
            
        # Determine winner based on scores
        winner_id = player1_id if player1_score > player2_score else player2_id
            
        return SingleMatch(
            player1_id=player1_id,
            player2_id=player2_id,
            player1_score=player1_score,
            player2_score=player2_score,
            winner_id=winner_id
        )

class DoubleMatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team1_pair_id = db.Column(db.Integer, db.ForeignKey('pair.id'), nullable=False)
    team2_pair_id = db.Column(db.Integer, db.ForeignKey('pair.id'), nullable=False)
    team1_score = db.Column(db.Integer, nullable=False)
    team2_score = db.Column(db.Integer, nullable=False)
    winner_pair_id = db.Column(db.Integer, db.ForeignKey('pair.id'), nullable=False)
    match_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Define relationships
    team1_pair = db.relationship('Pair', foreign_keys=[team1_pair_id])
    team2_pair = db.relationship('Pair', foreign_keys=[team2_pair_id])
    winner_pair = db.relationship('Pair', foreign_keys=[winner_pair_id])

    @staticmethod
    def create_match(team1_pair_id, team2_pair_id, team1_score, team2_score):
        # Verify pairs exist
        team1_pair = Pair.query.get(team1_pair_id)
        team2_pair = Pair.query.get(team2_pair_id)
        
        if not team1_pair or not team2_pair:
            raise ValueError("Both pairs must exist")
        
        if team1_pair_id == team2_pair_id:
            raise ValueError("Cannot have same pair on both teams")
            
        # Order teams (smaller pair ID becomes team1)
        if team1_pair_id > team2_pair_id:
            team1_pair_id, team2_pair_id = team2_pair_id, team1_pair_id
            team1_score, team2_score = team2_score, team1_score
            
        # Determine winner
        winner_pair_id = team1_pair_id if team1_score > team2_score else team2_pair_id
            
        return DoubleMatch(
            team1_pair_id=team1_pair_id,
            team2_pair_id=team2_pair_id,
            team1_score=team1_score,
            team2_score=team2_score,
            winner_pair_id=winner_pair_id
        )

with app.app_context():
    db.create_all()

@app.route('/pairs')
def pairs():
    pairs = Pair.query.all()
    return render_template('pairs.html', pairs=pairs)

@app.route('/add_pair', methods=['GET', 'POST'])
def add_pair():
    if request.method == 'POST':
        player1_id = int(request.form['player1'])
        player2_id = int(request.form['player2'])
        
        try:
            new_pair = Pair.create_pair(player1_id, player2_id)
            db.session.add(new_pair)
            db.session.commit()
            return redirect(url_for('pairs'))
        except ValueError as e:
            flash(str(e))
        except IntegrityError:
            db.session.rollback()
            flash('This pair already exists!')
            
    players = Player.query.order_by(Player.name).all()
    return render_template('add_pair.html', players=players)

@app.route('/')
@app.route('/players')
def players():
    try:
        players = Player.query.order_by(Player.name).all()
        print("**** ", players)
        return render_template('players.html', players=players)
    except Exception as e:
        flash(f"Error loading players: {str(e)}")
        return render_template('players.html', players=[])

@app.route('/add_player', methods=['GET', 'POST'])
def add_player():
    if request.method == 'POST':
        name = request.form['name']
        sex = request.form['sex']
        
        new_player = Player(
            name=name,
            sex=sex,
            join_date=datetime.utcnow()
        )
        db.session.add(new_player)
        db.session.commit()
        return redirect(url_for('players'))
    return render_template('add_player.html')

@app.route('/matches')
def matches():
    try:
        matches = SingleMatch.query.order_by(SingleMatch.match_date.desc()).all()
        return render_template('matches.html', matches=matches)
    except Exception as e:
        flash(f"Error loading matches: {str(e)}")
        return render_template('matches.html', matches=[])

@app.route('/add_match', methods=['GET', 'POST'])
def add_match():
    if request.method == 'POST':
        try:
            player1_id = int(request.form['player1'])
            player2_id = int(request.form['player2'])
            player1_score = int(request.form['player1_score'])
            player2_score = int(request.form['player2_score'])
            
            new_match = SingleMatch.create_match(
                player1_id, 
                player2_id, 
                player1_score, 
                player2_score
            )
            
            db.session.add(new_match)
            db.session.commit()
            return redirect(url_for('matches'))
            
        except ValueError as e:
            flash(str(e))
        except Exception as e:
            db.session.rollback()
            flash('Error recording match!')
            
    players = Player.query.order_by(Player.name).all()
    return render_template('add_match.html', players=players)

@app.route('/double_matches')
def double_matches():
    matches = DoubleMatch.query.order_by(DoubleMatch.match_date.desc()).all()
    return render_template('double_matches.html', matches=matches)

@app.route('/add_double_match', methods=['GET', 'POST'])
def add_double_match():
    if request.method == 'POST':
        try:
            team1_pair_id = int(request.form['team1_pair'])
            team2_pair_id = int(request.form['team2_pair'])
            team1_score = int(request.form['team1_score'])
            team2_score = int(request.form['team2_score'])
            
            new_match = DoubleMatch.create_match(
                team1_pair_id,
                team2_pair_id,
                team1_score,
                team2_score
            )
            
            db.session.add(new_match)
            db.session.commit()
            return redirect(url_for('double_matches'))
            
        except ValueError as e:
            flash(str(e))
        except Exception as e:
            db.session.rollback()
            flash('Error recording match!')
            
    pairs = Pair.query.all()
    return render_template('add_double_match.html', pairs=pairs)

if __name__ == '__main__':
    # app.run(debug=True)
    app.run(host='0.0.0.0', port=8080, debug=False)