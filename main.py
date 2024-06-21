from flask import Flask, render_template, request, redirect, url_for, send_from_directory, after_this_request, abort
from flask_wtf import FlaskForm
from wtforms import FileField, SubmitField
from werkzeug.utils import secure_filename
import os
import tempfile
import shutil
import uuid
from moviepy.editor import VideoFileClip, concatenate_videoclips
import re
import threading
import secrets  # Import the secrets module for random key generation

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)  # Generate a random 32-character hexadecimal string

app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()

# Define global variables to store video clips and paths
clip1 = None
clip2 = None
final_clip = None
video1_path = None
video2_path = None
output_path = None

class UploadForm(FlaskForm):
    """Form for uploading two videos."""
    video1 = FileField('First Video')
    video2 = FileField('Second Video')
    submit = SubmitField('Upload')

@app.route('/', methods=['GET', 'POST'])
def index():
    """Route for the main page where users upload videos."""
    form = UploadForm()
    if form.validate_on_submit():
        video1 = form.video1.data
        video2 = form.video2.data

        # Generate unique filenames for uploaded videos
        temp_filename1 = f"{uuid.uuid4().hex}_{secure_filename(video1.filename)}"
        temp_filename2 = f"{uuid.uuid4().hex}_{secure_filename(video2.filename)}"

        temp_video1_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename1)
        temp_video2_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename2)

        # Save uploaded videos to temporary folder
        video1.save(temp_video1_path)
        video2.save(temp_video2_path)

        print(f"Uploaded files are stored in: {app.config['UPLOAD_FOLDER']}")

        # Redirect to the editing page with uploaded video filenames as arguments
        return redirect(url_for('edit', video1=temp_filename1, video2=temp_filename2))
    return render_template('index.html', form=form)

@app.route('/edit')
def edit():
    """Route for editing page where users specify split point."""
    video1 = request.args.get('video1')
    video2 = request.args.get('video2')
    return render_template('edit.html', video1=video1, video2=video2)

@app.route('/process', methods=['POST'])
def process():
    """Route for processing videos based on user input."""
    global clip1, clip2, final_clip, video1_path, video2_path, output_path

    video1 = request.form['video1']
    video2 = request.form['video2']
    split_point_str = request.form['split_point']

    # Parse split_point_str in MM:SS:ms format into seconds
    match = re.match(r'(\d+):(\d{2}):(\d{3})', split_point_str)
    if not match:
        return "Invalid split point format. Please use MM:SS:ms format."

    minutes = int(match.group(1))
    seconds = int(match.group(2))
    milliseconds = int(match.group(3))

    split_point_seconds = minutes * 60 + seconds + milliseconds / 1000.0

    # Assign paths to the uploaded videos
    video1_path = os.path.join(app.config['UPLOAD_FOLDER'], video1)
    video2_path = os.path.join(app.config['UPLOAD_FOLDER'], video2)

    # Load video clips
    clip1 = VideoFileClip(video1_path)
    clip2 = VideoFileClip(video2_path)

    # Resize clip2 if its resolution doesn't match clip1
    if clip1.size != clip2.size:
        clip2 = clip2.resize(clip1.size)

    # Split clip1 at split_point_seconds
    part1 = clip1.subclip(0, split_point_seconds)
    part2 = clip1.subclip(split_point_seconds)

    # Concatenate part1, clip2, and part2
    final_clip = concatenate_videoclips([part1, clip2, part2])

    # Define output path
    output_filename = 'output.mp4'
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

    # Write final clip to output file
    final_clip.write_videofile(output_path, codec="libx264")

    # Render result page with the output video filename
    return render_template('result.html', output_video=output_filename)

@app.route('/download/<filename>')
def download_file(filename):
    """Route for downloading the processed video."""
    try:
        @after_this_request
        def cleanup(response):
            """Cleanup function to close video clips and delete temporary files."""
            try:
                # Close video clips
                clip1.close()
                clip2.close()
                final_clip.close()

                # Define delayed cleanup function
                def delayed_cleanup():
                    try:
                        # Remove temporary files
                        os.remove(video1_path)
                        os.remove(video2_path)
                        os.remove(output_path)
                    except Exception as e:
                        app.logger.error(f"Error cleaning up temporary files: {e}")

                # Schedule delayed cleanup (5 minutes)
                cleanup_timer = threading.Timer(300, delayed_cleanup)
                cleanup_timer.start()

            except Exception as e:
                app.logger.error(f"Error cleaning up temporary files: {e}")

            return response

        # Send the processed video file as an attachment for download
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

    except FileNotFoundError:
        abort(404)

@app.route('/send_file/<filename>')
def send_file(filename):
    """Route for sending any file from the upload folder."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)
