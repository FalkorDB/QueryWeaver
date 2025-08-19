"""Email service for sending invitation emails and notifications."""

import logging
import os
from typing import Tuple, Optional, Any
from flask import render_template_string

try:
    from flask_mail import Mail, Message
    FLASK_MAIL_AVAILABLE = True
except ImportError:
    FLASK_MAIL_AVAILABLE = False
    Mail = None
    Message = None


# Initialize Flask-Mail
mail: Optional[Any] = Mail() if FLASK_MAIL_AVAILABLE else None


def init_mail(app):
    """Initialize Flask-Mail with the Flask app."""
    if not FLASK_MAIL_AVAILABLE or mail is None:
        logging.warning("Flask-Mail is not available. Email functionality will be disabled.")
        return

    # Configure mail settings from environment variables
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', '587'))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

    mail.init_app(app)


def is_email_configured() -> bool:
    """Check if email configuration is properly set up."""
    if not FLASK_MAIL_AVAILABLE or mail is None:
        return False
    required_configs = ['MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_DEFAULT_SENDER']
    return all(os.getenv(config) for config in required_configs)


def send_organization_invitation(
    recipient_email: str,
    organization_name: str,
    organization_domain: str,
    admin_name: str,
    admin_email: str,
    app_url: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Send an organization invitation email to a user.
    
    Args:
        recipient_email: Email of the user being invited
        organization_name: Name of the organization
        organization_domain: Domain of the organization
        admin_name: Name of the admin who sent the invitation
        admin_email: Email of the admin who sent the invitation
        app_url: Base URL of the application (optional)
    
    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        if not is_email_configured():
            logging.warning("Email not configured. Skipping invitation email.")
            return False, "Email service not configured"

        # Default app URL if not provided
        if not app_url:
            app_url = os.getenv('APP_URL', 'http://localhost:5000')

        # Email template
        subject = f"Invitation to join {organization_name} on QueryWeaver"

        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{{ subject }}</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
                .content { background-color: #ffffff; padding: 20px; border: 1px solid #dee2e6; border-radius: 5px; }
                .button { display: inline-block; padding: 12px 24px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }
                .footer { margin-top: 20px; font-size: 0.9em; color: #6c757d; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🎉 You're invited to join {{ organization_name }}!</h2>
                </div>
                
                <div class="content">
                    <p>Hello,</p>
                    
                    <p><strong>{{ admin_name }}</strong> ({{ admin_email }}) has invited you to join the <strong>{{ organization_name }}</strong> organization on QueryWeaver.</p>
                    
                    <p>QueryWeaver is a powerful Text2SQL tool that transforms natural language into SQL queries using graph-powered schema understanding.</p>
                    
                    <p>To accept this invitation and start collaborating with your team:</p>
                    
                    <ol>
                        <li>Click the button below to sign in to QueryWeaver</li>
                        <li>Use your <strong>{{ recipient_email }}</strong> email address to log in</li>
                        <li>You'll automatically be added to the {{ organization_name }} organization</li>
                    </ol>
                    
                    <p style="text-align: center;">
                        <a href="{{ app_url }}" class="button">Sign in to QueryWeaver</a>
                    </p>
                    
                    <p><strong>Organization Details:</strong></p>
                    <ul>
                        <li><strong>Organization:</strong> {{ organization_name }}</li>
                        <li><strong>Domain:</strong> {{ organization_domain }}</li>
                        <li><strong>Invited by:</strong> {{ admin_name }} ({{ admin_email }})</li>
                    </ul>
                    
                    <p>If you have any questions, please contact {{ admin_name }} at {{ admin_email }}.</p>
                </div>
                
                <div class="footer">
                    <p><em>This invitation was sent by QueryWeaver on behalf of {{ admin_name }}.</em></p>
                    <p><em>If you believe you received this email in error, please ignore it.</em></p>
                </div>
            </div>
        </body>
        </html>
        """

        text_template = """
        You're invited to join {{ organization_name }}!
        
        Hello,
        
        {{ admin_name }} ({{ admin_email }}) has invited you to join the {{ organization_name }} organization on QueryWeaver.
        
        QueryWeaver is a powerful Text2SQL tool that transforms natural language into SQL queries using graph-powered schema understanding.
        
        To accept this invitation and start collaborating with your team:
        
        1. Visit: {{ app_url }}
        2. Use your {{ recipient_email }} email address to log in
        3. You'll automatically be added to the {{ organization_name }} organization
        
        Organization Details:
        - Organization: {{ organization_name }}
        - Domain: {{ organization_domain }}
        - Invited by: {{ admin_name }} ({{ admin_email }})
        
        If you have any questions, please contact {{ admin_name }} at {{ admin_email }}.
        
        ---
        This invitation was sent by QueryWeaver on behalf of {{ admin_name }}.
        If you believe you received this email in error, please ignore it.
        """

        # Render templates
        template_vars = {
            'subject': subject,
            'recipient_email': recipient_email,
            'organization_name': organization_name,
            'organization_domain': organization_domain,
            'admin_name': admin_name,
            'admin_email': admin_email,
            'app_url': app_url
        }

        html_body = render_template_string(html_template, **template_vars)
        text_body = render_template_string(text_template, **template_vars)

        # Create and send message
        if not FLASK_MAIL_AVAILABLE or mail is None or Message is None:
            return False, "Flask-Mail not available"

        msg = Message(
            subject=subject,
            recipients=[recipient_email],
            html=html_body,
            body=text_body
        )

        mail.send(msg)

        logging.info(
            "Invitation email sent successfully to %s for organization %s by admin %s",
            recipient_email, organization_name, admin_email
        )

        return True, "Invitation email sent successfully"

    except (ImportError, AttributeError) as e:
        logging.error(
            "Email service not properly configured: %s",
            str(e)
        )
        return False, "Email service not available"
    except Exception as e:  # pylint: disable=broad-except
        logging.error(
            "Failed to send invitation email to %s for organization %s: %s",
            recipient_email, organization_name, str(e)
        )
        return False, f"Failed to send invitation email: {str(e)}"


def send_organization_approval_notification(
    recipient_email: str,
    organization_name: str,
    organization_domain: str,
    app_url: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Send a notification email when a user's organization membership is approved.
    
    Args:
        recipient_email: Email of the user whose membership was approved
        organization_name: Name of the organization
        organization_domain: Domain of the organization
        app_url: Base URL of the application (optional)
    
    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        if not is_email_configured():
            logging.warning("Email not configured. Skipping approval notification email.")
            return False, "Email service not configured"

        # Default app URL if not provided
        if not app_url:
            app_url = os.getenv('APP_URL', 'http://localhost:5000')

        subject = f"Welcome to {organization_name} on QueryWeaver!"

        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{{ subject }}</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #d4edda; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
                .content { background-color: #ffffff; padding: 20px; border: 1px solid #dee2e6; border-radius: 5px; }
                .button { display: inline-block; padding: 12px 24px; background-color: #28a745; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }
                .footer { margin-top: 20px; font-size: 0.9em; color: #6c757d; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>✅ Your membership has been approved!</h2>
                </div>
                
                <div class="content">
                    <p>Hello,</p>
                    
                    <p>Great news! Your membership to the <strong>{{ organization_name }}</strong> organization on QueryWeaver has been approved.</p>
                    
                    <p>You can now access your organization's databases and start creating powerful SQL queries using natural language.</p>
                    
                    <p style="text-align: center;">
                        <a href="{{ app_url }}" class="button">Access QueryWeaver</a>
                    </p>
                    
                    <p><strong>Organization Details:</strong></p>
                    <ul>
                        <li><strong>Organization:</strong> {{ organization_name }}</li>
                        <li><strong>Domain:</strong> {{ organization_domain }}</li>
                    </ul>
                    
                    <p>Start exploring and enjoy using QueryWeaver!</p>
                </div>
                
                <div class="footer">
                    <p><em>This notification was sent by QueryWeaver.</em></p>
                </div>
            </div>
        </body>
        </html>
        """

        text_template = """
        Your membership has been approved!
        
        Hello,
        
        Great news! Your membership to the {{ organization_name }} organization on QueryWeaver has been approved.
        
        You can now access your organization's databases and start creating powerful SQL queries using natural language.
        
        Visit: {{ app_url }}
        
        Organization Details:
        - Organization: {{ organization_name }}
        - Domain: {{ organization_domain }}
        
        Start exploring and enjoy using QueryWeaver!
        
        ---
        This notification was sent by QueryWeaver.
        """

        # Render templates
        template_vars = {
            'subject': subject,
            'recipient_email': recipient_email,
            'organization_name': organization_name,
            'organization_domain': organization_domain,
            'app_url': app_url
        }

        html_body = render_template_string(html_template, **template_vars)
        text_body = render_template_string(text_template, **template_vars)

        # Create and send message
        if not FLASK_MAIL_AVAILABLE or mail is None or Message is None:
            return False, "Flask-Mail not available"

        msg = Message(
            subject=subject,
            recipients=[recipient_email],
            html=html_body,
            body=text_body
        )

        mail.send(msg)

        logging.info(
            "Approval notification email sent successfully to %s for organization %s",
            recipient_email, organization_name
        )

        return True, "Approval notification email sent successfully"

    except (ImportError, AttributeError) as e:
        logging.error(
            "Email service not properly configured: %s",
            str(e)
        )
        return False, "Email service not available"
    except Exception as e:  # pylint: disable=broad-except
        logging.error(
            "Failed to send approval notification email to %s for organization %s: %s",
            recipient_email, organization_name, str(e)
        )
        return False, f"Failed to send approval notification email: {str(e)}"
