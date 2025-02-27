from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from enum import Enum
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_
from sqlalchemy.orm import aliased

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
    is_active = db.Column(db.Boolean, default=True)
    elo_rating = db.Column(db.Float, default=1200.0)

class Pair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    elo_rating = db.Column(db.Float, default=1200.0)

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
    try:
        pairs = Pair.query.all()
        
        # Calculate win/loss records for each pair
        for pair in pairs:
            # Count wins (where this pair is the winner)
            wins = DoubleMatch.query.filter(
                DoubleMatch.winner_pair_id == pair.id
            ).count()
            
            # Count total matches (where this pair was team1 or team2)
            total_matches = DoubleMatch.query.filter(
                (DoubleMatch.team1_pair_id == pair.id) |
                (DoubleMatch.team2_pair_id == pair.id)
            ).count()
            
            # Calculate statistics
            pair.wins = wins
            pair.losses = total_matches - wins
            pair.total_matches = total_matches
            pair.win_rate = (wins / total_matches * 100) if total_matches > 0 else -1
        
        # Sort pairs by win rate (descending) and total matches (descending)
        pairs = sorted(pairs, 
                      key=lambda x: (x.elo_rating,  # 首先按ELO排序
                                   x.win_rate if x.win_rate >= 0 else float('-inf'),
                                   -x.total_matches),
                      reverse=True)
            
        template = 'ios/pairs.html' if is_ios() else 'pairs.html'
        return render_template(template, pairs=pairs)
    except Exception as e:
        flash(f"Error loading pairs: {str(e)}")
        template = 'ios/pairs.html' if is_ios() else 'pairs.html'
        return render_template(template, pairs=[])

@app.route('/add_pair', methods=['GET', 'POST'])
def add_pair():
    if request.method == 'POST':
        try:
            player1_id = int(request.form['player1'])
            player2_id = int(request.form['player2'])
            
            if player1_id == player2_id:
                flash('Cannot create a pair with the same player')
                return redirect(url_for('add_pair'))
            
            # Get both players
            player1 = Player.query.get(player1_id)
            player2 = Player.query.get(player2_id)
            
            # Order players by name
            if player1.name > player2.name:
                player1_id, player2_id = player2_id, player1_id
            
            # Check if pair already exists
            existing_pair = Pair.query.filter(
                ((Pair.player1_id == player1_id) & (Pair.player2_id == player2_id)) |
                ((Pair.player1_id == player2_id) & (Pair.player2_id == player1_id))
            ).first()
            
            if existing_pair:
                flash('This pair already exists!')
                return redirect(url_for('add_pair'))
            
            new_pair = Pair(player1_id=player1_id, player2_id=player2_id)
            db.session.add(new_pair)
            db.session.commit()
            return redirect(url_for('pairs'))
            
        except Exception as e:
            db.session.rollback()
            flash('Error creating pair!')
    
    # Get only active players
    active_players = Player.query.filter(Player.is_active == True).order_by(Player.name).all()
    
    # 根据设备类型选择模板
    template = 'ios/add_pair.html' if is_ios() else 'add_pair.html'
    return render_template(template, players=active_players)

@app.route('/')
@app.route('/players')
def players():
    try:
        players = Player.query.all()
        
        # Calculate win/loss records for each player
        for player in players:
            player_pairs = Pair.query.filter(
                (Pair.player1_id == player.id) | 
                (Pair.player2_id == player.id)
            ).all()
            
            pair_ids = [pair.id for pair in player_pairs]
            
            wins = DoubleMatch.query.filter(
                DoubleMatch.winner_pair_id.in_(pair_ids)
            ).count()
            
            total_matches = DoubleMatch.query.filter(
                (DoubleMatch.team1_pair_id.in_(pair_ids)) |
                (DoubleMatch.team2_pair_id.in_(pair_ids))
            ).count()
            
            player.wins = wins
            player.losses = total_matches - wins
            player.total_matches = total_matches
            player.win_rate = (wins / total_matches * 100) if total_matches > 0 else -1
        
        # Sort players by win rate (descending)
        players = sorted(players, 
                        key=lambda x: (x.elo_rating,  # 首先按ELO排序
                                     x.win_rate if x.win_rate >= 0 else float('-inf'), 
                                     -x.total_matches),
                        reverse=True)
            
        # 根据设备类型选择模板
        template = 'ios/players.html' if is_ios() else 'players.html'
        return render_template(template, players=players)
    except Exception as e:
        flash(f"Error loading players: {str(e)}")
        template = 'ios/players.html' if is_ios() else 'players.html'
        return render_template(template, players=[])

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
    template = 'ios/add_player.html' if is_ios() else 'add_player.html'
    return render_template(template)

@app.route('/double_matches')
def double_matches():
    matches = DoubleMatch.query.order_by(DoubleMatch.match_date.desc()).all()
    template = 'ios/double_matches.html' if is_ios() else 'double_matches.html'
    return render_template(template, matches=matches)

def calculate_elo_change(rating_a, rating_b, score_a, score_b, k_factor=32):
    """
    计算ELO评分变化
    rating_a: A方当前ELO评分
    rating_b: B方当前ELO评分
    score_a: A方得分
    score_b: B方得分
    k_factor: ELO系统的K因子，影响评分变化的幅度
    """
    # 计算胜率期望值
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    expected_b = 1 - expected_a
    
    # 计算实际得分（1=胜，0=负）
    actual_a = 1 if score_a > score_b else 0
    actual_b = 1 - actual_a
    
    # 计算评分变化
    change_a = k_factor * (actual_a - expected_a)
    change_b = k_factor * (actual_b - expected_b)
    
    return change_a, change_b

@app.route('/add_double_match', methods=['GET', 'POST'])
def add_double_match():
    if request.method == 'POST':
        try:
            team1_pair_id = int(request.form['team1_pair'])
            team2_pair_id = int(request.form['team2_pair'])
            team1_score = int(request.form['team1_score'])
            team2_score = int(request.form['team2_score'])
            
            # Validate different pairs
            if team1_pair_id == team2_pair_id:
                flash('Cannot record a match between the same pair')
                return redirect(url_for('add_double_match'))
            
            # Get both pairs to check for player overlap
            team1_pair = Pair.query.get(team1_pair_id)
            team2_pair = Pair.query.get(team2_pair_id)
            
            # Check for player overlap
            team1_players = {team1_pair.player1_id, team1_pair.player2_id}
            team2_players = {team2_pair.player1_id, team2_pair.player2_id}
            
            overlapping_players = team1_players & team2_players
            if overlapping_players:
                # Get the overlapping player(s) names
                overlapping_names = []
                for player_id in overlapping_players:
                    player = Player.query.get(player_id)
                    overlapping_names.append(player.name)
                
                # Format the error message
                error_msg = (
                    f"Player{'s' if len(overlapping_names) > 1 else ''} "
                    f"{', '.join(overlapping_names)} cannot play in both pairs:\n"
                    f"Team 1: {team1_pair.player1.name} / {team1_pair.player2.name}\n"
                    f"Team 2: {team2_pair.player1.name} / {team2_pair.player2.name}"
                )
                flash(error_msg)
                return redirect(url_for('add_double_match'))
            
            # Validate scores cannot be equal
            if team1_score == team2_score:
                flash('Scores cannot be equal - there must be a winner')
                return redirect(url_for('add_double_match'))
            
            # Create the match with the winner determined by scores
            winner_pair_id = team1_pair_id if team1_score > team2_score else team2_pair_id
            
            # 创建新比赛
            new_match = DoubleMatch(
                team1_pair_id=team1_pair_id,
                team2_pair_id=team2_pair_id,
                team1_score=team1_score,
                team2_score=team2_score,
                winner_pair_id=winner_pair_id
            )
            
            # 获取相关的配对
            team1_pair = Pair.query.get(team1_pair_id)
            team2_pair = Pair.query.get(team2_pair_id)
            
            # 更新配对的ELO评分
            pair_elo_change = calculate_elo_change(
                team1_pair.elo_rating,
                team2_pair.elo_rating,
                team1_score,
                team2_score
            )
            
            team1_pair.elo_rating += pair_elo_change[0]
            team2_pair.elo_rating += pair_elo_change[1]
            
            # 更新玩家的ELO评分（变化量减半，因为是团队比赛）
            player_elo_change = (pair_elo_change[0] / 2, pair_elo_change[1] / 2)
            
            # 更新team1的玩家
            team1_pair.player1.elo_rating += player_elo_change[0]
            team1_pair.player2.elo_rating += player_elo_change[0]
            
            # 更新team2的玩家
            team2_pair.player1.elo_rating += player_elo_change[1]
            team2_pair.player2.elo_rating += player_elo_change[1]
            
            # 保存所有更改
            db.session.add(new_match)
            db.session.commit()
            
            return redirect(url_for('double_matches'))
            
        except ValueError as e:
            flash('Invalid input: Please check your scores')
        except Exception as e:
            db.session.rollback()
            flash('Error recording match!')
    
    # Get pairs where both players are active using explicit aliases
    Player1 = aliased(Player)
    Player2 = aliased(Player)
    
    active_pairs = db.session.query(Pair)\
        .join(Player1, Pair.player1_id == Player1.id)\
        .join(Player2, Pair.player2_id == Player2.id)\
        .filter(
            db.and_(
                Player1.is_active == True,
                Player2.is_active == True
            )
        ).all()
    
    template = 'ios/add_double_match.html' if is_ios() else 'add_double_match.html'
    return render_template(template, pairs=active_pairs)

@app.route('/admin')
def admin():
    players = Player.query.order_by(Player.name).all()
    pairs = Pair.query.all()
    double_matches = DoubleMatch.query.order_by(DoubleMatch.match_date.desc()).all()
    template = 'ios/admin.html' if is_ios() else 'admin.html'
    return render_template(template, 
                         players=players,
                         pairs=pairs,
                         double_matches=double_matches)

@app.route('/delete/player/<int:id>', methods=['POST'])
def delete_player(id):
    try:
        player = Player.query.get_or_404(id)
        
        # Check if player is in any pairs
        pairs_count = Pair.query.filter(
            (Pair.player1_id == id) | 
            (Pair.player2_id == id)
        ).count()
        
        if pairs_count > 0:
            flash('Cannot delete player: Player is part of existing pairs. Please delete the pairs first.')
            return redirect(url_for('admin'))
        
        db.session.delete(player)
        db.session.commit()
        flash('Player deleted successfully')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting player: {str(e)}')
        
    return redirect(url_for('admin'))

@app.route('/delete/pair/<int:id>', methods=['POST'])
def delete_pair(id):
    try:
        pair = Pair.query.get_or_404(id)
        
        # Check if pair is involved in any matches
        matches_count = DoubleMatch.query.filter(
            (DoubleMatch.team1_pair_id == id) |
            (DoubleMatch.team2_pair_id == id)
        ).count()
        
        if matches_count > 0:
            flash('Cannot delete pair: Pair has played matches. Please delete the matches first.')
            return redirect(url_for('admin'))
        
        db.session.delete(pair)
        db.session.commit()
        flash('Pair deleted successfully')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting pair: {str(e)}')
        
    return redirect(url_for('admin'))

@app.route('/delete/double_match/<int:id>', methods=['POST'])
def delete_double_match(id):
    try:
        match = DoubleMatch.query.get_or_404(id)
        
        # 获取相关的配对
        team1_pair = match.team1_pair
        team2_pair = match.team2_pair
        
        # 计算原始ELO变化（用负分数来反转变化）
        pair_elo_change = calculate_elo_change(
            team1_pair.elo_rating,
            team2_pair.elo_rating,
            match.team2_score,  # 反转分数
            match.team1_score   # 反转分数
        )
        
        # 恢复配对的ELO评分
        team1_pair.elo_rating += pair_elo_change[0]
        team2_pair.elo_rating += pair_elo_change[1]
        
        # 恢复玩家的ELO评分
        player_elo_change = (pair_elo_change[0] / 2, pair_elo_change[1] / 2)
        
        # 恢复team1的玩家
        team1_pair.player1.elo_rating += player_elo_change[0]
        team1_pair.player2.elo_rating += player_elo_change[0]
        
        # 恢复team2的玩家
        team2_pair.player1.elo_rating += player_elo_change[1]
        team2_pair.player2.elo_rating += player_elo_change[1]
        
        # 删除比赛
        db.session.delete(match)
        db.session.commit()
        flash('Double match deleted successfully')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting match')
    return redirect(url_for('admin'))

@app.route('/toggle_player_status/<int:id>', methods=['POST'])
def toggle_player_status(id):
    try:
        player = Player.query.get_or_404(id)
        player.is_active = not player.is_active
        db.session.commit()
        return {'status': 'success', 'is_active': player.is_active}
    except Exception as e:
        db.session.rollback()
        return {'status': 'error', 'message': str(e)}, 400

def is_ios():
    user_agent = request.headers.get('User-Agent', '').lower()
    return any(device in user_agent for device in ['iphone', 'ipad'])

# 在创建Flask app后添加这个上下文处理器，使is_ios在所有模板中可用
@app.context_processor
def utility_processor():
    return dict(is_ios=is_ios)

if __name__ == '__main__':
    app.run(debug=False)
    #app.run(host='0.0.0.0', port=8080, debug=False)
