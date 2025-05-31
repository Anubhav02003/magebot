from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import os
import base64
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
import openai
from PIL import Image
import io

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Ensure upload directory exists
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    # Generate a unique session ID if not already set
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        session['messages'] = []
    
    return render_template('index.html')

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image part'}), 400
    
    file = request.files['image']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        # Create a unique filename
        filename = f"{session.get('session_id', str(uuid.uuid4()))}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Save the file
        file.save(filepath)
        
        # Store image path in session
        session['current_image'] = filepath
        
        # Add system message
        if 'messages' not in session:
            session['messages'] = []
        
        session['messages'].append({
            'role': 'system',
            'content': 'Image uploaded successfully. Ask me anything about this image!',
            'timestamp': datetime.now().isoformat()
        })
        session.modified = True
        
        return jsonify({
            'success': True,
            'image_url': f'/static/uploads/{filename}',
            'messages': session.get('messages', [])
        })
    
    return jsonify({'error': 'File upload failed'}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    
    # Add user message to history
    if 'messages' not in session:
        session['messages'] = []
    
    session['messages'].append({
        'role': 'user',
        'content': user_message,
        'timestamp': datetime.now().isoformat()
    })
    
    # Check if an image is uploaded
    image_path = session.get('current_image')
    if not image_path:
        ai_response = "Please upload an image first so I can analyze it and answer your questions."
    else:
        try:
            # Prepare image for OpenAI API
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Call OpenAI API with the image and the user's question
            response = openai.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that analyzes images and answers questions about them."
                    },
                    *[{"role": m["role"], "content": m["content"]} for m in session['messages'] if m["role"] in ["user", "assistant"]],
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_message},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            
            ai_response = response.choices[0].message.content
        except Exception as e:
            print(f"OpenAI API Error: {e}")
            ai_response = f"I'm sorry, I encountered an error while analyzing the image. Please try again later."
    
    # Add AI response to history
    session['messages'].append({
        'role': 'assistant',
        'content': ai_response,
        'timestamp': datetime.now().isoformat()
    })
    session.modified = True
    
    return jsonify({
        'response': ai_response,
        'messages': session.get('messages', [])
    })

@app.route('/api/clear', methods=['POST'])
def clear_chat():
    # Clear chat history but keep session
    session['messages'] = []
    if 'current_image' in session:
        del session['current_image']
    session.modified = True
    
    return jsonify({'success': True, 'messages': []})

if __name__ == '__main__':
    app.run(debug=True)