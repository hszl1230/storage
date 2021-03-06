# -*-coding:utf-8 -*-
from flask import render_template, redirect, url_for, flash, request, jsonify, g
from form import LoginForm, RegisterForm
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from model import User, Storage, Catalog, History
from . import db
import json
import datetime
import decimal


def init_views(app):
    class DataEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, datetime.datetime):
                return datetime.strftime(obj, '%Y-%m-%d %H:%M').replace(' 00:00', '')
            elif isinstance(obj, datetime.date):
                return datetime.strftime(obj, '%Y-%m-%d')
            elif isinstance(obj, decimal.Decimal):
                return str(obj)
            elif isinstance(obj, float):
                return round(obj, 8)
            return json.JSONEncoder.default(self, obj)

    # @app.template_filter('eip_format')
    def eip_format(data):
        return json.dumps(data, json.dumps, cls=DataEncoder, ensure_ascii=False, indent=2)

    @app.before_request
    def before_request():
        g.user = current_user
        g.para = {'iflogin': request.args.get('login_required') or 'default'}
        g.islogin = login()
        g.catalog = db.session.execute('SELECT ca.id, ca.catalog FROM stdb.catalog ca')

    # 登录
    @app.route('/', methods=['GET', 'POST'])
    @app.route('/index', methods=['GET', 'POST'])
    def index():
        if g.islogin == 'ok':
            return redirect(url_for('index'))
        elif g.islogin == 'mistake':
            return redirect('/index?login_required=1')
        g.para.update({'page': 'index'})
        return render_template('index.html',
                               login_form=LoginForm(),
                               para=g.para)

    # 是否登陆成功
    def login():
        login_form = LoginForm()
        if login_form.lg_submit.data and login_form.validate_on_submit():
            user = User.query.filter_by(username=login_form.username.data).first()
            # 验证密码
            if user is not None and user.verify_password(login_form.password.data):
                login_user(user, login_form.remember.data)
                return 'ok'
            flash(u'用户名或者密码错误！', 'error')
            return 'mistake'
        # 注册成功时显示flash
        if g.para == '2':
            flash(u'注册成功！现在您可以登录您的账号了', 'success')
        return 0

    # 注册
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        register_form = RegisterForm()
        if g.islogin == 'ok':
            return redirect(url_for('index'))
        elif g.islogin == 'mistake':
            return redirect('/register?login_required=1')
        if register_form.re_submit.data and register_form.validate_on_submit():
            user = User(email=register_form.email.data,
                        username=register_form.username.data,
                        password=register_form.password.data)
            db.session.add(user)
            db.session.commit()
            return redirect('/index?login_required=2')
        return render_template('register.html',
                               login_form=LoginForm(),
                               register_form=register_form,
                               para=g.para)

    # 登出
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect('#')

    # 库存查询
    @app.route('/storage', methods=['GET', 'POST'])
    def storage():
        para = {'page_index': request.args.get('page', 1, type=int),
                'catalog_id': request.args.get('catalog_id', ''),
                'query': request.args.get('query', ''),
                'part': request.args.get('part', ''),
                'id': request.args.get('id', ''),
                'sn': request.args.get('sn', ''),
                'username': request.args.get('username', ''),
                'location': request.args.get('location', ''),
                'state': request.args.get('state', '')}

        storages = db.session.query(Storage, Catalog).join(Catalog).filter('''
                (storage.catalog_id=:catalog_id or :catalog_id ='')
                and (storage.part like concat('%',:part,'%') or :part ='')
                and (storage.location like concat('%',:location,'%') or :location ='')
                and (storage.username like concat('%',:username,'%') or :username ='')
                and (storage.sn like concat('%',:sn,'%') or :sn ='')
                and (storage.id like concat('%',:id,'%') or :id ='')
                and (storage.state=:state or :state ='')
            ''').params(catalog_id=para['catalog_id'],
                        query=para['query'],
                        part=para['part'],
                        location=para['location'],
                        username=para['username'],
                        sn=para['sn'],
                        id=para['id'],
                        state=para['state']).order_by(Storage.id)
        pagination = storages.paginate(para['page_index'], per_page=15, error_out=False)
        storages = pagination.items

        g.para.update({'page': 'storage'})
        return render_template('storage.html',
                               login_form=LoginForm(),
                               para=g.para,
                               catalog=g.catalog,
                               page=eip_format(para),
                               storages=storages if para['query'] else [],
                               pagination=pagination if para['query'] else [])

    # 详情
    @app.route('/storage.detail', methods=['POST'])
    def detial():
        para = {'id': request.form.get('id')}
        part = db.session.execute(u'''
          select st.*,ca.catalog,
                CASE st.location WHEN '仓库' THEN '1' ELSE '0' END AS 'exit',
                CASE st.location WHEN '仓库' THEN '' ELSE 'disabled' END AS 'disabled'
          from stdb.storage st
          left join stdb.catalog ca on ca.id=st.catalog_id
          where st.id=:id
       ''', {'id': para['id']})
        part = [dict(r) for r in part]
        for k, v in part[0].items():
            if k == 'purchase_date':
                part[0][k] = v.strftime("%Y-%m-%d")
        return jsonify(part)

    # 保存
    @app.route('/storage.save', methods=['POST'])
    def save():
        sql = ''
        para = {'catalog_id': request.form.get('catalog_id', ''),
                'part': request.form.get('part', ''),
                'id': request.form.get('id', ''),
                'sn': request.form.get('sn', ''),
                'username': request.form.get('username', ''),
                'location': request.form.get('location', ''),
                'state': request.form.get('state', ''),
                'description': request.form.get('description', ''),
                # 不填默认今天
                'purchase_date': request.form.get('purchase_date') or datetime.datetime.today().strftime('%Y-%m-%d'),
                # 不填默认0元
                'price': request.form.get('price') or 0,
                'remark': request.form.get('remark', ''),
                'stype': request.form.get('type', ''),
                'ext': request.form.get('exit', ''),
                # 不填默认今天
                'register_date': request.form.get('register_date') or datetime.datetime.today().strftime('%Y-%m-%d'),}
        if para['stype'] == 'update':
            sql = '''
                UPDATE stdb.storage st
                    SET st.username=:username,
                        st.state=:state,
                        st.sn=:sn,
                        st.price=:price,
                        st.description=:description,
                        st.catalog_id=:catalog_id,
                        st.remark=:remark,
                        st.part=:part,
                        st.purchase_date=:purchase_date,
                        st.location=:location,
                        st.modify_date=now()
                    WHERE st.id=:id
            '''
        elif para['stype'] == 'insert':
            checkid = Storage.query.filter_by(id=para['id']).all()
            if len(checkid):
                return 'exist'
            sql = '''
            INSERT INTO stdb.storage
            (id,username,state,sn,price,description,catalog_id,remark,part,purchase_date,location,create_user,create_date)
            VALUE
            (:id,:username,:state,:sn,:price,:description,:catalog_id,:remark,:part,:purchase_date,:location,'admin',now())
            '''
        elif para['stype'] == 'history':
            sql = 'call history_p(:id, :username, :location, :ext, :register_date);'
        db.session.execute(sql, para)
        db.session.commit()
        return 'ok'

    @app.route('/storage.delete', methods=['POST'])
    def delete():
        para = request.form.get('id')
        db.session.execute("delete from stdb.storage where id='%s'" % para)
        db.session.commit()
        return 'ok'

    # 历史查询
    @app.route('/history', methods=['GET', 'POST'])
    def history():
        para = {'page_index': request.args.get('page', 1, type=int),
                'catalog_id': request.args.get('catalog_id', ''),
                'query': request.args.get('query', ''),
                'part': request.args.get('part', ''),
                'id': request.args.get('id', ''),
                'username': request.args.get('username', ''),
                'location': request.args.get('location', ''),
                'state': request.args.get('state', '')}

        historys = db.session.query(History, Storage.part, Catalog.catalog) \
            .outerjoin(Storage, Storage.id == History.part_id) \
            .outerjoin(Catalog, Catalog.id == Storage.catalog_id).filter('''
                (storage.catalog_id=:catalog_id or :catalog_id ='')
                and (storage.part like concat('%',:part,'%') or :part ='')
                and (st_history.location like concat('%',:location,'%') or :location ='')
                and (st_history.username like concat('%',:username,'%') or :username ='')
                and (st_history.part_id like concat('%',:id,'%') or :id ='')
                and (st_history.state=:state or :state ='')
            ''').params(catalog_id=para['catalog_id'],
                        query=para['query'],
                        part=para['part'],
                        location=para['location'],
                        username=para['username'],
                        id=para['id'],
                        state=para['state']).order_by(History.id.desc())
        pagination = historys.paginate(para['page_index'], per_page=15, error_out=False)
        historys = pagination.items

        g.para.update({'page': 'history'})
        return render_template('history.html',
                               login_form=LoginForm(),
                               para=g.para,
                               catalog=g.catalog,
                               page=eip_format(para),
                               historys=historys if para['query'] else [],
                               pagination=pagination if para['query'] else [])
