def Sign_up_email_body_template(username):
    return (f"""
<body style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 0;">
    <div style="max-width: 600px; margin: 20px auto; background: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1); text-align: center;">
        
        <!-- Logo -->
        <div style="padding: 10px 0;">
            <img src="" alt="C.H.I.K.I.T.S.A Logo" style="max-width: 150px;">
        </div>

        <!-- Content -->
        <h2 style="color: #1e88e5;">Welcome to C.H.I.K.I.T.S.A!</h2>
        <p style="color: #333; font-size: 16px;">Dear <strong>{username}</strong>,</p>
        <p style="color: #333; font-size: 14px;">Thank you for signing up! We are delighted to have you as part of our community dedicated to mental well-being.</p>
        <p style="color: #333; font-size: 14px;">Explore AI-powered mental health support, self-assessments, and insightful tools to enhance your wellness journey.</p>
        
        <p style="color: #333; font-size: 14px;">If you have any questions, feel free to reach out to our support team.</p>
        
        <!-- Footer -->
        <p style="color: #777; font-size: 12px; margin-top: 20px;">Stay strong, stay mindful!<br><strong>Team Suryaprabha</strong></p>
        <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
        <p style="color: #777; font-size: 12px;">&copy; 2025 C.H.I.K.I.T.S.A | All Rights Reserved</p>
        <p><a href="https://your-website.com" style="color: #1e88e5; text-decoration: none; font-size: 12px;">Visit our website</a></p>
    </div>
</body>
""")