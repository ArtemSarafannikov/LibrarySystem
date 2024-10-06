from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, LoginManager, login_required, login_user, current_user
from models.database import db, LDatabase
from datetime import datetime, date, timedelta


FINES_PER_DAY = 100

app = Flask(__name__)
app.config['SECRET_KEY'] = 'library_system_12354'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5433/library'

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


def check_fines(user_id: int) -> (float, list):
    user_books = LDatabase.UsersBooks.query.filter_by(user_id=user_id,
                                                      return_date=None).all()
    due_days = []
    fines = 0.0
    for ub in user_books:
        days = (ub.issue_date + timedelta(days=ub.book.due_days) - date.today()).days
        if days < 0:
            fines += abs(days) * FINES_PER_DAY
        due_days.append(days)

    return fines, due_days


def update_fines(user_id: int) -> (float, list):
    fines, due_days = check_fines(user_id)

    user = LDatabase.Users.query.get(user_id)
    user.fines = fines
    db.session.commit()
    return fines, due_days


@login_manager.user_loader
def load_user(user_id):
    return LDatabase.Users.query.get(int(user_id))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = LDatabase.Users.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Неверный логин или пароль')
    return render_template('login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    books = LDatabase.Books.query.all()
    user_books = LDatabase.UsersBooks.query.filter_by(user_id=current_user.id,
                                                      return_date=None).all()

    _, due_days = update_fines(current_user.id)

    return render_template('dashboard.html',
                           username=current_user.username,
                           books=books,
                           fines=current_user.fines,
                           is_admin=current_user.is_admin,
                           user_books=user_books,
                           due_days=due_days)


@app.route('/check_book', methods=['POST'])
@login_required
def check_book():
    title = request.form['title']
    book = LDatabase.Books.query.filter_by(title=title).first()
    if book:
        available = "Доступна" if book.available else "Не доступна"
        flash(f"Книга {book.title} ({available})")
    else:
        flash("Книга не найдена")
    return redirect(url_for('dashboard'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/add_book', methods=['POST'])
@login_required
def add_book():
    if not current_user.is_admin:
        flash('Недостаточно прав')
    else:
        title = request.form['title']
        author = request.form['author']
        new_book = LDatabase.Books(title=title, author=author)
        db.session.add(new_book)
        db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/delete_book', methods=['POST'])
@login_required
def delete_book():
    if not current_user.is_admin:
        flash('Недостаточно прав')
    else:
        title = request.form['title']
        book = LDatabase.Books.query.filter_by(title=title).first()
        if book:
            db.session.delete(book)
            db.session.commit()
        else:
            flash('Книга не найдена')
    return redirect(url_for('dashboard'))


@app.route('/issue_book', methods=["POST"])
@login_required
def issue_book():
    if not current_user.is_admin:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    title = request.form['title']
    username = request.form['username']

    book = LDatabase.Books.query.filter_by(title=title).first()
    if not book:
        flash('Такой книги не существует')
        return redirect(url_for('dashboard'))

    if not book.available:
        flash('Книга недоступна')
        return redirect(url_for('dashboard'))

    user = LDatabase.Users.query.filter_by(username=username).first()
    if not user:
        flash('Пользователь не найден')
        return redirect(url_for('dashboard'))

    book.available = False
    issued_book = LDatabase.UsersBooks(book_id=book.id, user_id=user.id)
    db.session.add(issued_book)
    db.session.commit()

    flash(f'Книга {book.title} выдана {user.username}')
    return redirect(url_for('dashboard'))


@app.route('/return_book', methods=['POST'])
@login_required
def return_book():
    if not current_user.is_admin:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    book_id = request.form['book_id']

    issued_book = LDatabase.UsersBooks.query.filter_by(book_id=book_id, return_date=None).first()
    if not issued_book:
        flash('Книга не найдена или уже возвращена')
        return redirect(url_for('dashboard'))

    fines, _ = update_fines(issued_book.user.id)

    issued_book.return_date = datetime.utcnow()
    issued_book.book.available = True
    db.session.commit()

    msg = f'Книга {issued_book.book.title} успешно возвращена'
    if fines > 0:
        msg += f'\nУ пользователя штраф {fines} руб'

    flash(msg)
    return redirect(url_for('dashboard'))


# TODO: Возможность пользователю бронировать книгу

# TODO: Продление срока сдачи книжки

# TODO: Запретить выдачу, если есть штраф больше 5000

# TODO: Общая статистика (общая задолженность, сколько книг на руках и т.д.)

# TODO: Поиск книги через индексирование

# TODO: Сделать взаимодействие с книгами через QR код (http://qrcoder.ru)


if __name__ == '__main__':
    app.run(debug=True)
