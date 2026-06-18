import os
import uuid
from flask import Flask, render_template, request, redirect, url_for
from flask_mysqldb import MySQL
from dotenv import load_dotenv
import boto3
from botocore.config import Config
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)

# =========================
# MYSQL CONFIG
# =========================
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# =========================
# AWS S3 CONFIG
# =========================
S3_BUCKET = os.getenv('S3_BUCKET')
AWS_REGION = os.getenv('AWS_REGION')

s3 = boto3.client(
    's3',
    region_name=AWS_REGION,
    config=Config(signature_version='s3v4')
)

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MANUAL_EXTENSIONS = {'pdf', 'doc', 'docx'}

# =========================
# HELPERS
# =========================
def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in IMAGE_EXTENSIONS


def allowed_manual(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in MANUAL_EXTENSIONS


def upload_to_s3(file, folder):
    key = f"{folder}/{uuid.uuid4().hex}_{secure_filename(file.filename)}"

    s3.upload_fileobj(file, S3_BUCKET, key)
    return key


def presigned_url(key):
    if not key:
        return None

    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': S3_BUCKET, 'Key': key},
        ExpiresIn=3600
    )

# =========================
# TABLE CREATION (MATCHES RDS)
# =========================
def create_tables():
    cur = mysql.connection.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS equipment (
            equipment_id INT AUTO_INCREMENT PRIMARY KEY,
            equipment_name VARCHAR(100),
            serial_number VARCHAR(100),
            department VARCHAR(100),
            purchase_date DATE,
            status VARCHAR(50),
            equipment_image VARCHAR(500),
            manual_file VARCHAR(500)
        )
    """)

    mysql.connection.commit()
    cur.close()


with app.app_context():
    create_tables()

# =========================
# ROUTES
# =========================

@app.route('/')
def index():
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT *
        FROM equipment
        ORDER BY equipment_id DESC
    """)

    equipment = cur.fetchall()
    cur.close()

    for item in equipment:
        item['image_url'] = presigned_url(item.get('equipment_image'))
        item['manual_url'] = presigned_url(item.get('manual_file'))

    return render_template('index.html', equipment=equipment)


@app.route('/add', methods=['GET', 'POST'])
def add_equipment():
    if request.method == 'POST':

        equipment_name = request.form['equipment_name']
        serial_number = request.form['serial_number']
        department = request.form['department']
        purchase_date = request.form['purchase_date']
        status = request.form['status']

        image_key = None
        manual_key = None

        file = request.files.get('equipment_image')
        if file and file.filename:
            image_key = upload_to_s3(file, 'equipment-images')

        file = request.files.get('manual_file')
        if file and file.filename:
            manual_key = upload_to_s3(file, 'manuals')

        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO equipment (
                equipment_name,
                serial_number,
                department,
                purchase_date,
                status,
                equipment_image,
                manual_file
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            equipment_name,
            serial_number,
            department,
            purchase_date,
            status,
            image_key,
            manual_key
        ))

        mysql.connection.commit()
        cur.close()

        return redirect('/')

    return render_template('add_equipment.html')


@app.route('/delete/<int:equipment_id>')
def delete_equipment(equipment_id):
    cur = mysql.connection.cursor()

    cur.execute(
        "DELETE FROM equipment WHERE equipment_id=%s",
        (equipment_id,)
    )

    mysql.connection.commit()
    cur.close()

    return redirect('/')


@app.route('/health')
def health():
    return {
        "status": "UP",
        "database": "CONNECTED"
    }


# =========================
# RUN APP
# =========================
if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )