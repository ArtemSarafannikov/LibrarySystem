from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_user, logout_user, LoginManager, login_required, login_user, current_user
from sqlalchemy import text
from sqlalchemy.orm import joinedload
from models.database import db, LDatabase
from models import BookModel
from datetime import datetime, date, timedelta
from math import ceil
import pandas as pd
from io import BytesIO

FINES_PER_DAY = 100
ELEMENTS_PER_PAGE = 10

app = Flask(__name__)
app.config['SECRET_KEY'] = 'library_system_12354'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5433/library'

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# Функция для подсчета штрафов
def check_fines(user_id: int) -> (float, list):
    # Берем информацию о всех книгах пользователя
    user_books = LDatabase.UsersBooks.query.filter_by(user_id=user_id,
                                                      return_date=None).all()
    due_days = []
    fines = 0.0
    for ub in user_books:
        # Проверяем сколько дней просрочено и начисляем в зависимости от этого штраф
        days = (ub.deadline_date - date.today()).days
        if days < 0:
            fines += abs(days) * FINES_PER_DAY
        due_days.append(days)

    return fines, due_days


# Функция для обновления информации о штрафах в базе данных
def update_fines(user_id: int) -> (float, list):
    # Получаем информацию о штрафах для конкретного пользователя
    fines, due_days = check_fines(user_id)

    # Записываем в бд
    user = LDatabase.Users.query.get(user_id)
    user.fines = fines
    db.session.commit()
    return fines, due_days


# Функция для LoginManager, чтобы он понимал какой пользователь из бд авторизовался
@login_manager.user_loader
def load_user(user_id):
    return LDatabase.Users.query.get(int(user_id))


# Главная страница, просто возвращаем шаблон
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        existing_user = LDatabase.Users.query.filter(LDatabase.Users.username == username).first()
        if existing_user:
            flash("Пользователь с таким email или username уже существует")
            return redirect(url_for('register'))

        new_user = LDatabase.Users(username=username,
                                   password=password,
                                   is_confirmed=False)
        db.session.add(new_user)
        db.session.commit()
        flash('Регистрация прошла успешно, ожидайте подтверждения администраторами')
        return redirect(url_for('login'))
    return render_template('register.html')


# Функция авторизации
@app.route('/login/', methods=['GET', 'POST'])
def login():
    # Если мы отправили данные на сервер (метод POST), то проверяем их по базе, если все верно - авторизуем
    if request.method == 'POST':
        query = request.args.get('next', '')
        username = request.form['username']
        password = request.form['password']
        user = LDatabase.Users.query.filter_by(username=username, is_confirmed=True).first()
        if user and user.password == password:
            login_user(user)
            if not query:
                return redirect(url_for('dashboard'))
            else:
                return redirect(query)
        else:
            flash('Неверный логин или пароль или аккаунт не подтвержден')
    return render_template('login.html')


# Функция для отображения каталога книг в библиотеке
@app.route('/books/', methods=['GET'])
def books():
    query = request.args.get('q', '')  # Берем аргумент из url
    page = request.args.get('page', 1, type=int)  # Берем аргумент из url
    pages = 1
    if not query:
        # Отображаем несколько книг на странице, используя пагинацию
        books = (LDatabase.Books.query.order_by(LDatabase.Books.available.desc(), LDatabase.Books.title)
                 .paginate(page=page, per_page=ELEMENTS_PER_PAGE, error_out=False))
        pages = ceil(LDatabase.Books.query.count() / ELEMENTS_PER_PAGE)
    else:
        # SQL запрос с использованием поиска
        sql_query = text(
            '''
            SELECT *,
                   ts_rank(to_tsvector('russian', title || ' ' || author), to_tsquery('russian', :query)) AS rank,
                   similarity(title, :query) AS sml
            FROM books
            WHERE to_tsvector('russian', title || ' ' || author) @@ to_tsquery('russian', :query) OR title % :query
            ORDER BY rank desc, sml desc
            LIMIT :elems_per_page
            OFFSET :offset
            '''
        )
        # Подставляем в sql запрос значения
        result = db.session.execute(sql_query, {'query': query.replace(' ', '_'),
                                                'elems_per_page': ELEMENTS_PER_PAGE,
                                                'offset': ELEMENTS_PER_PAGE * (page - 1)})
        books = []
        # Создаем список книг используя модель BookModel
        for record in result:
            books.append(BookModel.Book(id=str(record[0]),
                                        title=record[1],
                                        author=record[2],
                                        available=str(record[3]),
                                        due_days=str(record[4])))

        pages = ceil(len(books) / ELEMENTS_PER_PAGE)

    return render_template('books.html',
                           books=books,
                           query=query,
                           page=page,
                           num_of_pages=pages)


@app.route('/books/<int:book_id>')
@login_required
def book_info(book_id):
    book = LDatabase.Books.query.get_or_404(book_id)
    history = LDatabase.UsersBooks.query.filter_by(book_id=book_id).join(LDatabase.Users).all()
    reserved = (LDatabase.Reservation.query.
                  filter((LDatabase.Reservation.book_id == book_id) &
                         (LDatabase.Reservation.expiration_date >= date.today())).first())
    return render_template('book_info.html',
                           book=book,
                           history=history,
                           reserved=reserved)


# Функция для отображения личного кабинета
@app.route('/lk/')
@login_required
def dashboard():
    # Получаем список всех книг, закрепленных за пользователем
    user_books = LDatabase.UsersBooks.query.filter_by(user_id=current_user.id,
                                                      return_date=None).all()

    # Получаем список книг, забронированных пользователем
    now = date.today()
    reserved_books = (LDatabase.Reservation.query.join(LDatabase.Books).
                      filter((LDatabase.Reservation.user_id == current_user.id) &
                             (LDatabase.Reservation.expiration_date >= now) &
                             (LDatabase.Books.available)).all())

    # Получаем и обновляем информацию о штрафах
    _, due_days = update_fines(current_user.id)
    return render_template('dashboard.html',
                           username=current_user.username,
                           fines=current_user.fines,
                           is_admin=current_user.is_admin,
                           user_books=user_books,
                           due_days=due_days,
                           now_date=now,
                           reserved_books=reserved_books)


# Проверка доступности книги
@app.route('/check_book/', methods=['POST'])
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


# Выход из аккаунта
@app.route('/logout/')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# Добавление новой книги в каталог библиотеки
@app.route('/add_book/', methods=['POST'])
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


# Удаление книги из каталога библиотек
@app.route('/delete_book/', methods=['POST'])
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


# Аренда книги
@app.route('/issue_book/', methods=["POST"])
@login_required
def issue_book():
    # Проверяем, назначает администратор или кто-то другой
    if not current_user.is_admin:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    # Берем данные о названии книги и о пользователе
    book_id = request.form['id']
    user_id = request.form.get('user_id', -1, type=int)

    book = LDatabase.Books.query.get_or_404(book_id)
    # Если книги не существует в базе, то выводим ошибку
    if not book:
        flash('Такой книги не существует')
        return redirect(url_for('dashboard'))

    # Если книга не доступна в данный момент, то выводим ошибку
    if not book.available:
        flash('Книга недоступна')
        return redirect(url_for('dashboard'))

    if user_id == -1:
        username = request.form['username']
        # Получаем информацию о пользователе
        user = LDatabase.Users.query.filter_by(username=username).first()
    else:
        user = LDatabase.Users.query.get_or_404(user_id)
    # Если пользователь не найден, то выводим ошибку
    if not user:
        flash('Пользователь не найден')
        return redirect(url_for('dashboard'))

    # Получаем информацию о бронировании
    now = datetime.utcnow()
    reservation = (LDatabase.Reservation.query.filter_by(book_id=book.id)
                   .filter((LDatabase.Reservation.expiration_date >= now)).first())

    # Если забронирована, то выводим ошибку
    if reservation and reservation.user_id != user.id:
        flash(f"Книга забронирована пользователем {reservation.user.username}")
        return redirect(url_for('dashboard'))

    # Если штраф превышает 5000, то выводим ошибку
    if user.fines >= 5000:
        flash(f"Штраф пользователя составляет {user.fines}. Он не может брать книги, пока его не оплатит")
        return redirect(url_for('dashboard'))

    if reservation:
        reservation.expiration_date = date.today() - timedelta(days=1)

    # Если все условия соблюдены, то вешаем книгу на пользователя
    book.available = False
    deadline = request.form['due_days']
    issued_book = LDatabase.UsersBooks(book_id=book.id,
                                       user_id=user.id,
                                       deadline_date=datetime.now() + timedelta(days=int(deadline)))
    db.session.add(issued_book)
    db.session.commit()

    flash(f'Книга {book.title} выдана {user.username}')
    return redirect(url_for('dashboard'))


# Возврат книги
@app.route('/return_book/', methods=['POST'])
@login_required
def return_book():
    # Проверяем админ ли пытается совершить действие
    if not current_user.is_admin:
        flash('Недостаточно прав')
        return redirect(url_for('dashboard'))

    book_id = request.form['book_id']

    # Ищем книгу, которую хотят вернуть
    issued_book = LDatabase.UsersBooks.query.filter_by(book_id=book_id, return_date=None).first()
    # Если не найдена, то выводим ошибку
    if not issued_book:
        flash('Книга не найдена или уже возвращена')
        return redirect(url_for('dashboard'))

    # Обновляем штрафы
    fines, _ = update_fines(issued_book.user.id)

    # Возвращаем книгу
    issued_book.return_date = datetime.utcnow()
    issued_book.book.available = True
    db.session.commit()

    msg = f'Книга {issued_book.book.title} успешно возвращена'
    if fines > 0:
        msg += f'\nУ пользователя штраф {fines} руб'

    flash(msg)
    return redirect(url_for('dashboard'))


# Бронирование книги
@app.route('/reserve_book/', methods=['POST'])
@login_required
def reserve_book():
    # Получаем информацию о книге
    book_id = request.form['book_id']
    book = LDatabase.Books.query.get(book_id)

    # Если она недоступна, то не можем ее забронировать
    if not book.available:
        flash('Книга недоступна')
        return redirect(url_for('dashboard'))

    # Проверяем забронирована ли она уже или нет
    now = datetime.utcnow()
    exist = (LDatabase.Reservation.query.filter_by(book_id=book.id)
             .filter(LDatabase.Reservation.expiration_date >= now)).first()
    if exist:
        flash("Книга уже забронирована")
        return redirect(url_for('dashboard'))

    # Если не забронироваан обновляем информацию в базе данных
    reservation = LDatabase.Reservation(book_id=book.id, user_id=current_user.id)
    db.session.add(reservation)
    db.session.commit()

    flash(f"Книга {book.title} успешно забронирована вами. Заберите её до {reservation.expiration_date}")
    return redirect(url_for('dashboard'))


# Отмена брони
@app.route('/cancel_reserve/', methods=['POST'])
@login_required
def cancel_reserve():
    # Получаем информацию о бронировании
    reservation_id = request.form['reservation_id']
    reservation = LDatabase.Reservation.query.get(reservation_id)

    # Удаляем информацию о бронировании
    db.session.delete(reservation)
    db.session.commit()
    flash("Бронь успешно отменена")
    return redirect(url_for('dashboard'))


@app.route('/admin/')
@login_required
def admin():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    return render_template('admin.html', is_admin=current_user.is_admin)


@app.route('/admin/users/')
@login_required
def admin_users():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    query = request.args.get('q', '')
    if query:
        users = LDatabase.Users.query.filter(LDatabase.Users.username.like(f"%{query}%")).all()
    else:
        users = LDatabase.Users.query.all()
    return render_template('admin_users.html', users=users)


@app.route('/admin/users/<int:user_id>')
@login_required
def admin_user_info(user_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    update_fines(user_id)
    user = LDatabase.Users.query.get_or_404(user_id)
    history = LDatabase.UsersBooks.query.filter_by(user_id=user_id).join(LDatabase.Books).all()
    return render_template('admin_user_info.html',
                           user=user,
                           history=history,
                           now_date=date.today())


@app.route('/admin/change_deadline', methods=['POST'])
@login_required
def change_deadline():
    if current_user.is_admin:
        deadline = request.form['deadline']
        id = request.form['id']
        user_book = LDatabase.UsersBooks.query.get_or_404(id)
        user_book.deadline_date = deadline
        db.session.commit()
    else:
        flash('У вас нет доступа')
    return redirect(url_for('dashboard'))


@app.route('/admin/confirm_user', methods=['POST'])
@login_required
def confirm_user():
    if current_user.is_admin:
        id = request.form['user_id']
        user = LDatabase.Users.query.get_or_404(id)
        user.is_confirmed = True
        db.session.commit()
    else:
        flash('У вас нет доступа')
    return redirect(url_for('admin_users'))


@app.route('/admin/statistic')
@login_required
def admin_statistic():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    total_fines = db.session.query(db.func.sum(LDatabase.Users.fines)).scalar()
    total_books_on_loan = LDatabase.Books.query.filter_by(available=False).count()
    books = (db.session.query(LDatabase.UsersBooks).filter_by(return_date=None)
             .join(LDatabase.Users)
             .join(LDatabase.Books).options(
                    joinedload(LDatabase.UsersBooks.user),
                    joinedload(LDatabase.UsersBooks.book)
    ).all())

    return render_template('admin_statistic.html',
                           total_fines=total_fines,
                           total_books_on_loan=total_books_on_loan,
                           books_on_loan=books)


@app.route('/admin/statistic/export')
@login_required
def export_statistic():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    books = (db.session.query(LDatabase.UsersBooks).filter_by(return_date=None)
             .join(LDatabase.Users)
             .join(LDatabase.Books).options(
        joinedload(LDatabase.UsersBooks.user),
        joinedload(LDatabase.UsersBooks.book)
    ).all())

    data = []
    for record in books:
        data.append({
            'username': record.user.username,
            'book_title': record.book.title,
            'deadline': record.deadline_date,
        })

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Книги на руках')
    output.seek(0)
    return send_file(output,
                     as_attachment=True,
                     download_name=f'library_statistic_{datetime.now()}.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# TODO: Сделать взаимодействие с книгами через QR код (https://goqr.me/api/)

# TODO: Красивый интерфейс


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
