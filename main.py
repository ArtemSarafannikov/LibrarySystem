from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, LoginManager, login_required, login_user, current_user
from models.database import db, LDatabase

app = Flask(__name__)
app.config['SECRET_KEY'] = 'library_system_12354'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5433/library'

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


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
    return render_template('dashboard.html',
                           username=current_user.username,
                           books=books,
                           fines=current_user.fines,
                           is_admin=current_user.is_admin)


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


# TODO: Добавить админу возможность вешать книгу на пользователя

# TODO: Возможность пользователю бронировать книгу

# TODO: Поиск книги через индексирование

# TODO: Сделать взаимодействие с книгами через QR код (http://qrcoder.ru)


if __name__ == '__main__':
    app.run(debug=True)
