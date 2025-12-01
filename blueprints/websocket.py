from flask import Blueprint, render_template, request, jsonify, session, flash
from extensions import socketio
from flask_socketio import emit, join_room
from utils.session import check_session_validity
from services.websocket_service import (
    get_websocket_status,
    get_websocket_subscriptions,
    subscribe_to_symbols,
    unsubscribe_from_symbols,
    unsubscribe_all,
    register_market_data_callback
)
from database.symbol import enhanced_search_symbols
from database.auth_db import get_api_key_for_tradingview, get_broker_name
from utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)

# Create blueprint
websocket_bp = Blueprint('websocket_bp', __name__, url_prefix='/websocket')

@websocket_bp.route('/')
@check_session_validity
def index():
    """Render the WebSocket management page"""
    username = session.get('user')
    if username:
        # Register callback to emit data to this user's room
        def on_market_data(data):
            # Emit to the specific user's room
            socketio.emit('market_data', data, room=f"user_{username}")
            
        register_market_data_callback(username, on_market_data)
        
    return render_template('websocket.html')

@socketio.on('connect')
def handle_connect():
    """Handle Socket.IO connection"""
    username = session.get('user')
    if username:
        join_room(f"user_{username}")
        logger.info(f"User {username} connected to Socket.IO and joined room user_{username}")

@websocket_bp.route('/search')
@check_session_validity
def search():
    """Search for symbols to subscribe"""
    query = request.args.get('q', '').strip()
    exchange = request.args.get('exchange')
    
    if not query:
        return jsonify([])
    
    try:
        results = enhanced_search_symbols(query, exchange)
        return jsonify([{
            'symbol': r.symbol,
            'name': r.name,
            'exchange': r.exchange,
            'token': r.token,
            'instrumenttype': r.instrumenttype
        } for r in results])
    except Exception as e:
        logger.error(f"Error searching symbols: {e}")
        return jsonify({'error': str(e)}), 500

@websocket_bp.route('/subscriptions')
@check_session_validity
def get_subscriptions():
    """Get current subscriptions"""
    username = session.get('user')
    if not username:
        return jsonify({'error': 'User not logged in'}), 401
        
    success, data, status_code = get_websocket_subscriptions(username)
    if success:
        return jsonify(data)
    else:
        return jsonify(data), status_code

def _get_broker_and_parse_symbols(username, symbols_list):
    """Helper to get broker and parse symbols"""
    api_key = get_api_key_for_tradingview(username)
    if not api_key:
        return None, None, "API Key not found"
        
    broker = get_broker_name(api_key)
    if not broker:
        return None, None, "Broker not found"
        
    parsed_symbols = []
    for s in symbols_list:
        if ':' in s:
            exchange, symbol = s.split(':', 1)
            parsed_symbols.append({'exchange': exchange, 'symbol': symbol})
        else:
            # Default to NSE if no exchange provided, or handle as error?
            # For now assuming NSE if not provided, or just passing as is if logic allows
            parsed_symbols.append({'exchange': 'NSE', 'symbol': s})
            
    return broker, parsed_symbols, None

@websocket_bp.route('/subscribe', methods=['POST'])
@check_session_validity
def subscribe():
    """Subscribe to a symbol"""
    username = session.get('user')
    if not username:
        return jsonify({'error': 'User not logged in'}), 401
        
    data = request.json
    symbols = data.get('symbols', [])
    
    if not symbols:
        return jsonify({'error': 'No symbols provided'}), 400
        
    broker, parsed_symbols, error = _get_broker_and_parse_symbols(username, symbols)
    if error:
        return jsonify({'error': error}), 400
        
    success, response, status_code = subscribe_to_symbols(username, broker, parsed_symbols)
    return jsonify(response), status_code

@websocket_bp.route('/unsubscribe', methods=['POST'])
@check_session_validity
def unsubscribe():
    """Unsubscribe from a symbol"""
    username = session.get('user')
    if not username:
        return jsonify({'error': 'User not logged in'}), 401
        
    data = request.json
    symbols = data.get('symbols', [])
    
    if not symbols:
        return jsonify({'error': 'No symbols provided'}), 400
        
    broker, parsed_symbols, error = _get_broker_and_parse_symbols(username, symbols)
    if error:
        return jsonify({'error': error}), 400
        
    success, response, status_code = unsubscribe_from_symbols(username, broker, parsed_symbols)
    return jsonify(response), status_code

@websocket_bp.route('/status')
@check_session_validity
def status():
    """Get WebSocket connection status"""
    username = session.get('user')
    if not username:
        return jsonify({'error': 'User not logged in'}), 401
        
    success, data, status_code = get_websocket_status(username)
    return jsonify(data), status_code
