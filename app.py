from flask import Flask, render_template, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('landing.html')

@app.route('/api/stats')
def get_stats():
    """API endpoint for platform statistics"""
    stats = {
        'mental_health_impact': {
            'global_affected': 970000000,
            'india_youth_impact': 52,
            'productivity_loss': 87000000000000  # 87 trillion INR
        },
        'platform_metrics': {
            'diagnostic_accuracy': 87,
            'user_retention': 90,
            'appointment_booking': 85,
            'user_satisfaction': 4.7
        },
        'market_opportunity': {
            'india_tam': 37000000000,
            'global_tam': 567000000000,
            'target_segments': {
                'b2c': 60,
                'b2b': 30,
                'educational': 10
            }
        },
        'working_features': [
            'AI Chatbot (Seraphis)',
            'Comprehensive Questionnaires',
            'Wellness Reports',
            'Appointment Booking',
            'Mood Analytics',
            'Meditation Modules',
            'Progress Tracking',
            'Multi-language Support'
        ],
        'limited_features': [
            'Real-time Emotion Detection',
            'Gamified Tap-Impulse Test',
            'Video/Audio Behavioral Analysis',
            'Wellness Journey Visualization',
            'Multimodal AI Analysis'
        ]
    }
    return jsonify(stats)

if __name__ == '__main__':
    app.run(debug=True)
