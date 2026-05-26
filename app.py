from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from datetime import datetime, timedelta
import unicodedata
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = "lab-system-secret-key"

# =========================
# TÀI KHOẢN ĐĂNG NHẬP
# =========================

TECH_EMAIL = "Quocbao151023@gmail.com"
TECH_PASSWORD = "p4ssw0rd"
TECH_NAME = "Quốc Bảo"


# =========================
# GOOGLE SHEET CONFIG
# =========================

GOOGLE_CREDENTIALS_FILE = "key.json"

BOOKING_SPREADSHEET_ID = "16eguXNHfCzbTq6olAQaMQBAylkqNR3gjVMmtnAkSBpE"
HANDOVER_SPREADSHEET_ID = "1nmIwGAMIFnuAfv-EWGG9yubxjifodxvsX2Iyzx0fJRU"

BOOKING_SHEET_NAME = "LAB_BOOKING"
HANDOVER_SHEET_NAME = "LAB_HANDOVER"
ATTENDANCE_SHEET_NAME = "LAB_ATTENDANCE"


# =========================
# GOOGLE SHEET CONNECT
# =========================

def get_google_client(readonly=False):
    if readonly:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly"
        ]
    else:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=scopes
    )

    return gspread.authorize(credentials)


client = get_google_client(readonly=False)


def get_sheet_rows(spreadsheet_id, sheet_name):
    google_client = get_google_client(readonly=True)
    spreadsheet = google_client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)
    return worksheet.get_all_records()


def get_lab_booking_rows():
    return get_sheet_rows(
        BOOKING_SPREADSHEET_ID,
        BOOKING_SHEET_NAME
    )


def get_lab_handover_rows():
    return get_sheet_rows(
        HANDOVER_SPREADSHEET_ID,
        HANDOVER_SHEET_NAME
    )


def get_booking_spreadsheet_for_write():
    return client.open_by_key(BOOKING_SPREADSHEET_ID)

def get_or_create_attendance_sheet():
    spreadsheet = get_booking_spreadsheet_for_write()

    try:
        sheet = spreadsheet.worksheet(ATTENDANCE_SHEET_NAME)
    except Exception:
        sheet = spreadsheet.add_worksheet(
            title=ATTENDANCE_SHEET_NAME,
            rows=1000,
            cols=10
        )

        sheet.append_row([
            "Dấu thời gian",
            "Mã sinh viên",
            "Họ tên",
            "Mã đăng ký",
            "Lab",
            "Ngày",
            "Ca",
            "Loại",
            "Trạng thái điểm danh",
            "Người điểm danh"
        ])

    return sheet


def get_attendance_rows():
    try:
        sheet = get_or_create_attendance_sheet()
        return sheet.get_all_records()
    except Exception:
        return []


def make_attendance_key(booking_id, student_id, name, lab, date, shift):
    return "|".join([
        clean_value(booking_id),
        clean_value(student_id),
        clean_value(name).lower(),
        clean_value(lab),
        clean_value(date),
        clean_value(shift)
    ])

# =========================
# HELPER FUNCTIONS
# =========================

def clean_value(value):
    if value is None:
        return ""
    return str(value).strip()


def remove_vietnamese_accents(text):
    text = str(text or "")
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        char for char in text
        if unicodedata.category(char) != "Mn"
    )
    text = text.replace("đ", "d").replace("Đ", "D")
    return text


def normalize_text(value):
    return remove_vietnamese_accents(clean_value(value)).lower().replace(" ", "")


def normalize_yes_no_py(value):
    text = remove_vietnamese_accents(clean_value(value)).lower()

    if text in ["co", "yes", "true", "1"]:
        return "CO"

    if text in ["khong", "no", "false", "0"]:
        return "KHONG"

    return text.upper()


def get_value_by_possible_keys(row, keys):
    for key in keys:
        if key in row:
            value = clean_value(row.get(key))
            if value:
                return value

    normalized_row = {
        clean_value(k): v
        for k, v in row.items()
    }

    for key in keys:
        key_clean = clean_value(key)
        if key_clean in normalized_row:
            value = clean_value(normalized_row.get(key_clean))
            if value:
                return value

    row_by_normalized_key = {
        normalize_text(k): v
        for k, v in row.items()
    }

    for key in keys:
        key_norm = normalize_text(key)
        if key_norm in row_by_normalized_key:
            value = clean_value(row_by_normalized_key.get(key_norm))
            if value:
                return value

    return ""


def extract_lab_from_id_key(id_key):
    if not id_key:
        return ""

    text = str(id_key).strip().upper()

    if text.startswith("L1-"):
        return "Lab 1"
    if text.startswith("L2-"):
        return "Lab 2"
    if text.startswith("L3-"):
        return "Lab 3"

    return ""


def extract_shift_from_id_key(id_key):
    if not id_key:
        return ""

    text = str(id_key).strip().upper()

    if "-C1-" in text:
        return "Ca 1"
    if "-C2-" in text:
        return "Ca 2"
    if "-C3-" in text:
        return "Ca 3"
    if "-C4-" in text:
        return "Ca 4"

    return ""


def extract_lab_from_slot_key(slot_key):
    if not slot_key:
        return ""

    parts = str(slot_key).split("|")

    for part in parts:
        part = part.strip()
        if part.lower().startswith("lab"):
            return part

    return ""


def extract_shift_from_slot_key(slot_key):
    if not slot_key:
        return ""

    parts = str(slot_key).split("|")

    for part in parts:
        part = part.strip()
        if part.lower().startswith("ca"):
            return part

    return ""


def format_date_for_calendar(raw_date):
    raw_date = clean_value(raw_date)

    if not raw_date:
        return ""

    formats = [
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass

    return ""


def parse_notification_date(raw_date):
    raw_date = clean_value(raw_date)

    if not raw_date:
        return None

    formats = [
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(raw_date, fmt)
        except Exception:
            pass

    return None


def is_within_notification_window(raw_date):
    date_obj = parse_notification_date(raw_date)

    if not date_obj:
        return False

    now = datetime.now()
    start_date = now - timedelta(days=7)
    end_date = now + timedelta(days=7)

    return start_date <= date_obj <= end_date


def parse_group_members(member_text):
    members = []

    member_text = clean_value(member_text)

    if not member_text:
        return members

    lines = member_text.replace(";", "\n").replace(",", "\n").split("\n")

    for line in lines:
        text = line.strip()

        if not text:
            continue

        if "." in text:
            first_part = text.split(".", 1)[0].strip()
            if first_part.isdigit():
                text = text.split(".", 1)[1].strip()

        if "–" in text:
            parts = text.split("–")
        elif "-" in text:
            parts = text.split("-")
        else:
            parts = [text]

        name = parts[0].strip()
        student_id = ""

        if len(parts) > 1:
            student_id = parts[1].strip()

        if name or student_id:
            members.append({
                "name": name,
                "student_id": student_id
            })

    return members


# =========================
# PAGE ROUTES + LOGIN
# =========================

@app.route("/", methods=["GET", "POST"])
def login():
    error = None

    # Khi mở link gốc 127.0.0.1:5000/
    # luôn hiện giao diện đăng nhập trước
    if request.method == "GET":
        session.clear()
        return render_template("login.html", error=error)

    # Khi bấm đăng nhập
    email = request.form.get("email")
    password = request.form.get("password")

    if email == TECH_EMAIL and password == TECH_PASSWORD:
        session["user"] = TECH_NAME
        return redirect(url_for("dashboard"))

    error = "Sai email hoặc mật khẩu"
    return render_template("login.html", error=error)


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        user=session["user"]
    )


@app.route("/attendance")
def attendance():
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template(
        "attendance.html",
        user=session["user"]
    )


@app.route("/cleaning-report")
def cleaning_report():
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template(
        "cleaning_report.html",
        user=session["user"]
    )


@app.route("/lab-performance")
def lab_performance():
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template(
        "lab_performance.html",
        user=session["user"]
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================
# API THÔNG BÁO TỪ SHEET
# =========================

@app.route("/api/notifications")
def api_notifications():
    try:
        bookings = get_lab_booking_rows()
        handovers = get_lab_handover_rows()

        notifications = []

        for row in bookings:
            status = get_value_by_possible_keys(row, [
                "TRẠNG THÁI",
                "TRANG THAI"
            ])

            if status != "ĐÃ_XÁC_NHẬN":
                continue

            id_key = get_value_by_possible_keys(row, [
                "ID_KEY"
            ])

            name = get_value_by_possible_keys(row, [
                "1. Họ và tên của bạn là:",
                "1. Họ và tên của bạn là: ",
                "Họ và tên của bạn là:",
                "Họ và tên"
            ])

            slot_key = get_value_by_possible_keys(row, [
                "SLOT_KEY"
            ])

            lab = (
                get_value_by_possible_keys(row, [
                    "6. Phòng lab được lựa chọn là:",
                    "6. Phòng Lab được lựa chọn là:",
                    "Phòng lab được lựa chọn là:",
                    "Phòng Lab",
                    "Lab"
                ])
                or extract_lab_from_slot_key(slot_key)
                or extract_lab_from_id_key(id_key)
            )

            shift = (
                get_value_by_possible_keys(row, [
                    "9. Ca bạn đăng ký sử dụng là:",
                    "9. Ca bạn đăng ký sử dụng là: ",
                    "Ca bạn đăng ký sử dụng là:",
                    "Ca"
                ])
                or extract_shift_from_slot_key(slot_key)
                or extract_shift_from_id_key(id_key)
            )

            use_date = get_value_by_possible_keys(row, [
                "8. Ngày bạn đăng ký sử dụng phòng là:",
                "Ngày bạn đăng ký sử dụng phòng là:",
                "Ngày đăng ký",
                "Ngày sử dụng"
            ])

            support = get_value_by_possible_keys(row, [
                "10. Bạn có cần hỗ trợ kỹ thuật không?",
                "11. Bạn có cần hỗ trợ kỹ thuật không?",
                "Cần hỗ trợ kỹ thuật",
                "Hỗ trợ kỹ thuật"
            ])

            if not id_key:
                continue

            if not is_within_notification_window(use_date):
                continue

            support_text = remove_vietnamese_accents(str(support)).lower()
            need_support = (
                "co" in support_text
                or "có" in str(support).lower()
            )

            if need_support:
                notifications.append({
                    "notification_id": f"booking-support-{id_key}",
                    "type": "booking_support",
                    "title": "THÔNG BÁO ĐĂNG KÝ - YÊU CẦU KTV",
                    "message": f"{name} đã đăng ký {lab} - {shift}",
                    "id_key": id_key,
                    "date": use_date,
                    "level": "warning"
                })
            else:
                notifications.append({
                    "notification_id": f"booking-{id_key}",
                    "type": "booking",
                    "title": "THÔNG BÁO ĐĂNG KÝ PHÒNG LAB",
                    "message": f"{name} đã đăng ký {lab} - {shift}",
                    "id_key": id_key,
                    "date": use_date,
                    "level": "info"
                })

        for row in handovers:
            id_key = get_value_by_possible_keys(row, [
                "1. ID_KEY của bạn là:",
                "ID_KEY",
                "ID_KEY của bạn là:"
            ])

            student_name = get_value_by_possible_keys(row, [
                "3. Họ và tên của bạn là:",
                "5. Họ và tên của bạn là:",
                "Họ và tên"
            ])

            process_status = get_value_by_possible_keys(row, [
                "PROCESS_STATUS"
            ])

            error_message = get_value_by_possible_keys(row, [
                "ERROR_MESSAGE"
            ])

            abnormal = get_value_by_possible_keys(row, [
                "10. Phòng Lab có phát sinh vấn đề bất thường trong quá trình sử dụng không?",
                "Phòng Lab có phát sinh vấn đề bất thường trong quá trình sử dụng không?"
            ])

            handover_date = get_value_by_possible_keys(row, [
                "Dấu thời gian",
                "UPDATED_AT"
            ])

            abnormal_text = remove_vietnamese_accents(str(abnormal)).lower()

            has_problem = False

            if process_status == "ERROR":
                has_problem = True

            if error_message:
                has_problem = True

            if "co" in abnormal_text or "có" in str(abnormal).lower():
                has_problem = True

            if has_problem and id_key and is_within_notification_window(handover_date):
                notifications.append({
                    "notification_id": f"handover-{id_key}",
                    "type": "handover_problem",
                    "title": "CÓ VẤN ĐỀ BÀN GIAO",
                    "message": error_message or f"{student_name} báo có vấn đề bàn giao",
                    "id_key": id_key,
                    "date": handover_date,
                    "level": "danger"
                })

        notifications.sort(
            key=lambda item: parse_notification_date(item.get("date")) or datetime.min,
            reverse=True
        )

        notifications = notifications[:30]

        return jsonify({
            "success": True,
            "count": len(notifications),
            "data": notifications
        })

    except Exception as e:
        print("API NOTIFICATIONS ERROR:", e)

        return jsonify({
            "success": False,
            "count": 0,
            "data": [],
            "error": str(e)
        }), 500


# =========================
# API LỊCH PHÒNG LAB
# =========================

@app.route("/api/bookings")
def get_bookings():
    try:
        rows = get_lab_booking_rows()
        bookings = []

        for row in rows:
            status = get_value_by_possible_keys(row, [
                "TRẠNG THÁI",
                "TRANG THAI"
            ])

            if status != "ĐÃ_XÁC_NHẬN":
                continue

            raw_date = get_value_by_possible_keys(row, [
                "8. Ngày bạn đăng ký sử dụng phòng là:",
                "Ngày bạn đăng ký sử dụng phòng là:",
                "Ngày đăng ký"
            ])

            formatted_date = format_date_for_calendar(raw_date)

            if not formatted_date:
                continue

            id_key = get_value_by_possible_keys(row, [
                "ID_KEY",
                "1. ID_KEY của bạn là:"
            ])

            slot_key = get_value_by_possible_keys(row, [
                "SLOT_KEY"
            ])

            lab = (
                get_value_by_possible_keys(row, [
                    "6. Phòng lab được lựa chọn là:",
                    "6. Phòng Lab được lựa chọn là:",
                    "Phòng lab được lựa chọn là:",
                    "Phòng Lab",
                    "Lab"
                ])
                or extract_lab_from_slot_key(slot_key)
                or extract_lab_from_id_key(id_key)
            )

            shift = (
                get_value_by_possible_keys(row, [
                    "9. Ca bạn đăng ký sử dụng là: ",
                    "9. Ca bạn đăng ký sử dụng là:",
                    "Ca bạn đăng ký sử dụng là:",
                    "Ca"
                ])
                or extract_shift_from_slot_key(slot_key)
                or extract_shift_from_id_key(id_key)
            )

            name = get_value_by_possible_keys(row, [
                "1. Họ và tên của bạn là: ",
                "1. Họ và tên của bạn là:",
                "Họ và tên của bạn là:",
                "Họ và tên"
            ])

            bookings.append({
                "name": name,
                "lab": lab,
                "shift": shift,
                "date": formatted_date,
                "status": status,
                "idKey": id_key
            })

        return jsonify(bookings)

    except Exception as e:
        print("API BOOKINGS ERROR:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================
# API THEO DÕI ĐIỂM DANH
# =========================

@app.route("/api/attendance-bookings")
def attendance_bookings():
    try:
        rows = get_lab_booking_rows()
        attendance_rows = get_attendance_rows()

        filter_date = clean_value(request.args.get("date", ""))
        filter_lab = clean_value(request.args.get("lab", ""))
        filter_shift = clean_value(request.args.get("shift", ""))
        filter_status = clean_value(request.args.get("status", ""))

        latest_status = {}

        for att in attendance_rows:
            key = make_attendance_key(
                get_value_by_possible_keys(att, ["Mã đăng ký"]),
                get_value_by_possible_keys(att, ["Mã sinh viên"]),
                get_value_by_possible_keys(att, ["Họ tên"]),
                get_value_by_possible_keys(att, ["Lab"]),
                get_value_by_possible_keys(att, ["Ngày"]),
                get_value_by_possible_keys(att, ["Ca"])
            )

            status = get_value_by_possible_keys(att, ["Trạng thái điểm danh"])

            if key and status:
                latest_status[key] = status

        data = []

        for row in rows:
            status = get_value_by_possible_keys(row, [
                "TRẠNG THÁI",
                "TRANG THAI"
            ])

            if status != "ĐÃ_XÁC_NHẬN":
                continue

            id_key = get_value_by_possible_keys(row, ["ID_KEY"])
            slot_key = get_value_by_possible_keys(row, ["SLOT_KEY"])

            register_type = get_value_by_possible_keys(row, [
                "5. Bạn đăng ký với tư cách là:",
                "Bạn đăng ký với tư cách là:"
            ])

            name = get_value_by_possible_keys(row, [
                "1. Họ và tên của bạn là: ",
                "1. Họ và tên của bạn là:",
                "Họ và tên của bạn là:",
                "Họ và tên"
            ])

            student_id = get_value_by_possible_keys(row, [
                "2. Mã số sinh viên của bạn là:",
                "Mã số sinh viên của bạn là:",
                "MSSV"
            ])

            lab = (
                get_value_by_possible_keys(row, [
                    "6. Phòng lab được lựa chọn là:",
                    "6. Phòng Lab được lựa chọn là:",
                    "Phòng lab được lựa chọn là:",
                    "Phòng",
                    "Lab"
                ])
                or extract_lab_from_slot_key(slot_key)
                or extract_lab_from_id_key(id_key)
            )

            date = get_value_by_possible_keys(row, [
                "8. Ngày bạn đăng ký sử dụng phòng là:",
                "Ngày bạn đăng ký sử dụng phòng là:",
                "Ngày đăng ký"
            ])

            shift = (
                get_value_by_possible_keys(row, [
                    "9. Ca bạn đăng ký sử dụng là: ",
                    "9. Ca bạn đăng ký sử dụng là:",
                    "Ca bạn đăng ký sử dụng là:",
                    "Ca"
                ])
                or extract_shift_from_slot_key(slot_key)
                or extract_shift_from_id_key(id_key)
            )

            member_list = get_value_by_possible_keys(row, [
                "5.2. Danh sách thành viên nhóm là: (Họ tên 1 - MSSV 1; Họ tên 2 - MSSV 2; ...) ",
                "5.2. Danh sách thành viên nhóm là: (Họ tên 1 - MSSV 1; Họ tên 2 - MSSV 2; ...)",
                "5.2. Danh sách thành viên nhóm là:",
                "Danh sách thành viên nhóm là:"
            ])

            if not name and not student_id:
                continue

            main_key = make_attendance_key(id_key, student_id, name, lab, date, shift)

            data.append({
                "booking_id": id_key,
                "register_type": register_type,
                "name": name,
                "student_id": student_id,
                "lab": lab,
                "date": date,
                "shift": shift,
                "role": "Người đăng ký chính",
                "raw_members": member_list,
                "attendance_status": latest_status.get(main_key, "Chưa điểm danh")
            })

            if register_type == "Nhóm" and member_list:
                members = parse_group_members(member_list)

                for member in members:
                    member_key = make_attendance_key(
                        id_key,
                        member["student_id"],
                        member["name"],
                        lab,
                        date,
                        shift
                    )

                    data.append({
                        "booking_id": id_key,
                        "register_type": "Nhóm",
                        "name": member["name"],
                        "student_id": member["student_id"],
                        "lab": lab,
                        "date": date,
                        "shift": shift,
                        "role": "Thành viên nhóm",
                        "raw_members": member_list,
                        "attendance_status": latest_status.get(member_key, "Chưa điểm danh")
                    })

                filtered_data = []

        for item in data:
            item_date = clean_value(item.get("date", ""))
            item_lab = clean_value(item.get("lab", ""))
            item_shift = clean_value(item.get("shift", ""))
            item_status = clean_value(item.get("attendance_status", ""))

            if filter_date:
                item_date_formatted = format_date_for_calendar(item_date)
                if item_date_formatted != filter_date:
                    continue

            if filter_lab and filter_lab not in ["Tất cả Lab", "all"]:
                if item_lab != filter_lab:
                    continue

            if filter_shift and filter_shift not in ["Tất cả ca", "all"]:
                if item_shift != filter_shift:
                    continue

            if filter_status and filter_status not in ["Tất cả trạng thái", "all"]:
                if item_status != filter_status:
                    continue

            filtered_data.append(item)
        return jsonify({
            "success": True,
            "data": filtered_data
        })

    except Exception as e:
        print("API ATTENDANCE BOOKINGS ERROR:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
# =========================
# API LƯU TRẠNG THÁI ĐIỂM DANH
# =========================

@app.route("/api/save-attendance-status", methods=["POST"])
def save_attendance_status():
    try:
        data = request.get_json()
        spreadsheet = get_booking_spreadsheet_for_write()

        try:
            sheet = spreadsheet.worksheet(ATTENDANCE_SHEET_NAME)
        except Exception:
            sheet = spreadsheet.add_worksheet(
                title=ATTENDANCE_SHEET_NAME,
                rows=1000,
                cols=10
            )

            sheet.append_row([
                "Dấu thời gian",
                "Mã sinh viên",
                "Họ tên",
                "Mã đăng ký",
                "Lab",
                "Ngày",
                "Ca",
                "Loại",
                "Trạng thái điểm danh",
                "Người điểm danh"
            ])

        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        sheet.append_row([
            now,
            data.get("student_id", ""),
            data.get("name", ""),
            data.get("booking_id", ""),
            data.get("lab", ""),
            data.get("date", ""),
            data.get("shift", ""),
            data.get("role", ""),
            data.get("attendance_status", ""),
            "Kỹ thuật viên"
        ])

        return jsonify({
            "success": True
        })

    except Exception as e:
        print("API SAVE ATTENDANCE ERROR:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================
# API BÁO CÁO VỆ SINH / BÀN GIAO
# =========================

@app.route("/api/cleaning-report")
def api_cleaning_report():
    try:
        bookings = get_lab_booking_rows()
        handovers = get_lab_handover_rows()

        handover_map = {}

        for handover in handovers:
            id_key = get_value_by_possible_keys(handover, [
                "1. ID_KEY của bạn là:",
                "ID_KEY",
                "ID_KEY của bạn là:"
            ])

            if id_key:
                handover_map[id_key] = handover

        report_data = []

        for booking in bookings:
            id_key = get_value_by_possible_keys(booking, [
                "ID_KEY",
                "1. ID_KEY của bạn là:"
            ])

            if not id_key:
                continue

            status_booking = get_value_by_possible_keys(booking, [
                "TRẠNG THÁI"
            ])

            if status_booking and status_booking != "ĐÃ_XÁC_NHẬN":
                continue

            handover = handover_map.get(id_key)

            slot_key_booking = get_value_by_possible_keys(booking, [
                "SLOT_KEY"
            ])

            lab = (
                get_value_by_possible_keys(booking, [
                    "6. Phòng lab được lựa chọn là:",
                    "6. Phòng Lab được lựa chọn là:",
                    "9. Phòng Lab bạn đã sử dụng là:",
                    "Phòng",
                    "Lab"
                ])
                or extract_lab_from_slot_key(slot_key_booking)
                or extract_lab_from_id_key(id_key)
            )

            shift = (
                get_value_by_possible_keys(booking, [
                    "9. Ca bạn đăng ký sử dụng là: ",
                    "9. Ca bạn đăng ký sử dụng là:",
                    "8. Ca bạn đăng ký sử dụng là:",
                    "Ca"
                ])
                or extract_shift_from_slot_key(slot_key_booking)
                or extract_shift_from_id_key(id_key)
            )

            booking_date = get_value_by_possible_keys(booking, [
                "8. Ngày bạn đăng ký sử dụng phòng là:",
                "Ngày đăng ký",
                "Dấu thời gian"
            ])

            if handover:
                process_status = get_value_by_possible_keys(handover, [
                    "PROCESS_STATUS"
                ])

                if process_status == "DONE":
                    status = "Đã bàn giao"
                else:
                    status = "Cần kiểm tra"

                slot_key_handover = get_value_by_possible_keys(handover, [
                    "SLOT_KEY"
                ])

                handover_lab = (
                    get_value_by_possible_keys(handover, [
                        "7. Phòng Lab bạn đã sử dụng là:",
                        "9. Phòng Lab bạn đã sử dụng là:",
                        "Phòng",
                        "Lab"
                    ])
                    or extract_lab_from_slot_key(slot_key_handover)
                    or extract_lab_from_id_key(id_key)
                )

                handover_shift = (
                    extract_shift_from_slot_key(slot_key_handover)
                    or extract_shift_from_id_key(id_key)
                )

                report_data.append({
                    "id_key": id_key,
                    "lab": lab or handover_lab,
                    "shift": shift or handover_shift,
                    "booking_date": booking_date,
                    "handover_date": get_value_by_possible_keys(handover, [
                        "Dấu thời gian",
                        "UPDATED_AT"
                    ]),
                    "handover_student": (
                        get_value_by_possible_keys(handover, [
                            "3. Họ và tên của bạn là:",
                            "5. Họ và tên của bạn là:",
                            "Họ và tên"
                        ])
                        or "--"
                    ),
                    "status": status,
                    "before_image": get_value_by_possible_keys(handover, [
                        "12. Hình ảnh minh chứng trạng thái phòng Lab trước khi sử dụng:",
                        "14. Hình ảnh minh chứng trạng thái phòng Lab trước khi sử dụng:"
                    ]),
                    "after_image": get_value_by_possible_keys(handover, [
                        "14. Hình ảnh minh chứng trạng thái phòng Lab sau khi sử dụng/ vệ sinh:",
                        "17. Hình ảnh minh chứng trạng thái phòng Lab sau khi sử dụng/ vệ sinh:"
                    ]),
                    "folder_link": get_value_by_possible_keys(handover, [
                        "DRIVE_FOLDER_LINK"
                    ]),
                    "slot_folder_link": get_value_by_possible_keys(handover, [
                        "SLOT_FOLDER_LINK"
                    ]),
                    "error_message": get_value_by_possible_keys(handover, [
                        "ERROR_MESSAGE"
                    ])
                })

            else:
                report_data.append({
                    "id_key": id_key,
                    "lab": lab,
                    "shift": shift,
                    "booking_date": booking_date,
                    "handover_date": "--",
                    "handover_student": "--",
                    "status": "Chưa bàn giao",
                    "before_image": "",
                    "after_image": "",
                    "folder_link": "",
                    "slot_folder_link": "",
                    "error_message": ""
                })

        return jsonify({
            "success": True,
            "data": report_data
        })

    except Exception as e:
        print("API CLEANING REPORT ERROR:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================
# API HIỆU SUẤT PHÒNG LAB
# =========================

@app.route("/api/lab-performance")
def api_lab_performance():
    try:
        bookings = get_lab_booking_rows()
        handovers = get_lab_handover_rows()

        handover_map = {}

        for handover in handovers:
            id_key = get_value_by_possible_keys(handover, [
                "1. ID_KEY của bạn là:",
                "ID_KEY",
                "ID_KEY của bạn là:"
            ])

            if id_key:
                handover_map[id_key] = handover

        performance_data = []

        for booking in bookings:
            id_key = get_value_by_possible_keys(booking, [
                "ID_KEY",
                "1. ID_KEY của bạn là:"
            ])

            if not id_key:
                continue

            status = get_value_by_possible_keys(booking, [
                "TRẠNG THÁI"
            ])

            if status != "ĐÃ_XÁC_NHẬN":
                continue

            slot_key = get_value_by_possible_keys(booking, [
                "SLOT_KEY"
            ])

            lab = (
                get_value_by_possible_keys(booking, [
                    "6. Phòng lab được lựa chọn là:",
                    "6. Phòng Lab được lựa chọn là:",
                    "Phòng",
                    "Lab"
                ])
                or extract_lab_from_slot_key(slot_key)
                or extract_lab_from_id_key(id_key)
            )

            shift = (
                get_value_by_possible_keys(booking, [
                    "9. Ca bạn đăng ký sử dụng là: ",
                    "9. Ca bạn đăng ký sử dụng là:",
                    "Ca"
                ])
                or extract_shift_from_slot_key(slot_key)
                or extract_shift_from_id_key(id_key)
            )

            booking_date = get_value_by_possible_keys(booking, [
                "8. Ngày bạn đăng ký sử dụng phòng là:",
                "Ngày đăng ký",
                "Dấu thời gian"
            ])

            purpose = get_value_by_possible_keys(booking, [
                "6. Mục đích đăng ký sử dụng phòng Lab là:",
                "6. Mục đích đăng ký sử dụng phòng lab là:",
                "Mục đích đăng ký sử dụng phòng Lab",
                "Mục đích đăng ký sử dụng phòng lab",
                "Mục đích sử dụng phòng Lab",
                "Mục đích sử dụng phòng lab",
                "Mục đích sử dụng",
                "Mục đích"
            ])

            need_support = get_value_by_possible_keys(booking, [
                "10. Bạn có cần hỗ trợ kỹ thuật không?",
                "11. Bạn có cần hỗ trợ kỹ thuật không?",
                "Cần hỗ trợ kỹ thuật",
                "Hỗ trợ kỹ thuật"
            ])

            handover = handover_map.get(id_key)

            is_handover = False
            abnormal_after = False

            if handover:
                process_status = get_value_by_possible_keys(handover, [
                    "PROCESS_STATUS"
                ])

                if process_status == "DONE":
                    is_handover = True

                abnormal_after_text = get_value_by_possible_keys(handover, [
                    "10. Phòng Lab có phát sinh vấn đề bất thường trong quá trình sử dụng không?",
                    "15. Phòng Lab có gì bất thường sau khi sử dụng không?",
                    "15. Phòng lab có gì bất thường sau khi sử dụng không?"
                ])

                abnormal_after = normalize_yes_no_py(abnormal_after_text) == "CO"

            performance_data.append({
                "id_key": id_key,
                "lab": lab,
                "shift": shift,
                "date": booking_date,
                "purpose": purpose or "Khác",
                "need_support": normalize_yes_no_py(need_support) == "CO",
                "is_handover": is_handover,
                "abnormal_after": abnormal_after
            })

        return jsonify({
            "success": True,
            "data": performance_data
        })

    except Exception as e:
        print("API LAB PERFORMANCE ERROR:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================
# API TEST KẾT NỐI SHEET
# =========================

@app.route("/api/test-sheets")
def test_sheets():
    try:
        booking_rows = get_lab_booking_rows()
        handover_rows = get_lab_handover_rows()

        return jsonify({
            "success": True,
            "booking_sheet_id": BOOKING_SPREADSHEET_ID,
            "handover_sheet_id": HANDOVER_SPREADSHEET_ID,
            "booking_sheet_name": BOOKING_SHEET_NAME,
            "handover_sheet_name": HANDOVER_SHEET_NAME,
            "booking_rows": len(booking_rows),
            "handover_rows": len(handover_rows)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(debug=True)
