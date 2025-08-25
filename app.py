from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask import Flask, render_template, request

import pandas as pd
import os
from supabase import create_client, Client
SUPABASE_URL = "https://lrtnwgpksqxvwachjyus.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxydG53Z3Brc3F4dndhY2hqeXVzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU5NTUyNTAsImV4cCI6MjA3MTUzMTI1MH0.oA0kPIoy3RvFXlRRwWFQ06PMggN6RiqvNsnhchjBGro"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = 'change_this_secret_key'



# Inscription
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        nom = request.form.get('nom')
        groupe = request.form.get('groupe')
        result = supabase.auth.sign_up({"email": email, "password": password})
        if result.user:
            user_id = result.user.id
            supabase.table('profiles').insert({
                "id": user_id,
                "nom": nom,
                "groupe": groupe
            }).execute()
            flash("Inscription réussie, vous pouvez vous connecter.", "success")
            return redirect(url_for('login'))
        else:
            flash("Erreur lors de l'inscription.", "danger")
    return render_template('register.html')

# Connexion
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        result = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if result.user:
            session['user_id'] = result.user.id
            profile = supabase.table('profiles').select('*').eq('id', result.user.id).single().execute().data
            session['nom'] = profile['nom'] if profile else None
            session['groupe'] = profile['groupe'] if profile else None
            session['is_admin'] = True  # Ajouté pour permettre l'accès à la vue admin
            return redirect(url_for('dashboard', view='admin'))
        else:
            flash("Identifiants invalides.", "danger")
    return render_template('login.html')



@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))




UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'upload')
CSV_PATH = os.path.join(UPLOAD_DIR, 'completion-mn072025-20250823_1539-comma_separated.csv')

@app.route('/upload', methods=['POST'])
def upload():
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))
    file = request.files.get('csvfile')
    if file and file.filename.endswith('.csv'):
        file.save(CSV_PATH)
        session['upload_message'] = "Fichier CSV mis à jour avec succès."
    else:
        session['upload_message'] = "Erreur : fichier non valide."
    return redirect(url_for('dashboard', view='admin'))

def load_data():
    if not os.path.exists(CSV_PATH):
        return None, None, {}
    df = pd.read_csv(CSV_PATH)
    # Masquer les colonnes de date d’achèvement
    date_cols = [col for col in df.columns if 'Date d’achèvement' in col]
    df_no_dates = df.drop(columns=date_cols)
    # Renommer chaque colonne module avec un identifiant unique (ex: M2C_1, M2C_2, ...)
    module_map = {}
    module_code_cols = {}
    module_name_map = {}
    for col in df_no_dates.columns:
        if col.startswith('M'):
            code = col.split()[0]
            module_code_cols.setdefault(code, []).append(col)
            # Récupère le nom exact du module (tout sauf le code)
            module_name = col[len(code):].strip()
            module_name_map[col] = module_name if module_name else code
    for code, cols in module_code_cols.items():
        if len(cols) > 1:
            for idx, col in enumerate(cols, 1):
                module_map[col] = f"{code}_{idx}"
                module_name_map[f"{code}_{idx}"] = module_name_map[col]
        else:
            module_map[cols[0]] = code
            module_name_map[code] = module_name_map[cols[0]]
    df_no_dates = df_no_dates.rename(columns=module_map)
    # module_name_map : {code_module: nom_exact}
    # Remplacer les valeurs 'Terminé (note minimale de réussite atteinte)' par 'Terminé'
    df_no_dates = df_no_dates.replace('Terminé (note minimale de réussite atteinte)', 'Terminé')
    # Remplacer les valeurs 'Terminé (n’a pas atteint la note minimale de réussite)' par 'Pas terminé'
    df_no_dates = df_no_dates.replace('Terminé (n’a pas atteint la note minimale de réussite)', 'Pas terminé')
    # Remplacer 'Terminé' et 'Pas terminé' par des emojis
    df_no_dates = df_no_dates.replace('Terminé', '✅')
    df_no_dates = df_no_dates.replace('Pas terminé', '❌')
    # Ajouter la colonne 'Cours terminé' : ✅ si tous les modules sont terminés, ❌ sinon
    module_cols = [col for col in df_no_dates.columns if col.startswith('M')]
    def cours_termine(row):
        # Vérifie que toutes les colonnes modules existent et valent '✅' (comparaison sur str)
        vals = [str(row[col]) for col in module_cols if col in row]
        return '✅' if vals and all(val == '✅' for val in vals) else '❌'
    df_no_dates['Cours terminé'] = df_no_dates.apply(cours_termine, axis=1)
    # Formater les ID sur 3 chiffres séquentiels
    if 'ID' in df_no_dates.columns:
        df_no_dates['ID'] = [f"{i+1:03d}" for i in range(len(df_no_dates))]
    return df, df_no_dates, module_name_map

@app.route('/', methods=['GET'])
def dashboard():
    search = request.args.get('search', '')
    view = request.args.get('view', 'simple')  # 'admin' ou 'simple'
    is_admin = session.get('is_admin', False)
    upload_message = session.pop('upload_message', None)
    if view == 'admin' and not is_admin:
        return redirect(url_for('login'))
    df, df_no_dates, module_name_map = load_data()
    if df is None or df_no_dates is None:
        return render_template(
            'dashboard.html',
            data=None,
            columns=None,
            module_columns=None,
            module_name_map=None,
            completed_count=None,
            not_completed_count=None,
            completion_rate=None,
            activity_completion=None,
            module_names=None,
            learners=None,
            feedbacks=None,
            current_year=None,
            total_learners=None,
            search=search,
            view=view,
            is_admin=is_admin,
            upload_message=upload_message,
            no_data=True
        )
    # Liste des noms des personnes ayant terminé et n'ayant pas terminé (après load_data)
    completers = df_no_dates[df_no_dates['Cours terminé'] == '✅']['Nom'].tolist() if 'Cours terminé' in df_no_dates.columns and 'Nom' in df_no_dates.columns else []
    non_completers = df_no_dates[df_no_dates['Cours terminé'] == '❌']['Nom'].tolist() if 'Cours terminé' in df_no_dates.columns and 'Nom' in df_no_dates.columns else []
    # Statistiques pour le tableau de bord
    total_apprenants = len(df_no_dates)
    total_cours_termines = (df_no_dates['Cours terminé'] == '✅').sum()
    total_cours_non_termines = (df_no_dates['Cours terminé'] == '❌').sum()
    # Statistiques par module : pourcentage d’achèvement
    # Pour chaque colonne module, calcule le pourcentage d’achèvement individuellement
    module_percent = []
    for col in df_no_dates.columns:
        if col.startswith('M'):
            percent = round((df_no_dates[col] == '✅').sum() / total_apprenants * 100, 1) if total_apprenants > 0 else 0
            module_percent.append((col, percent))
    stats = {
        'total_apprenants': total_apprenants,
        'total_cours_termines': total_cours_termines,
        'total_cours_non_termines': total_cours_non_termines,
        'module_percent': module_percent
    }
    # Recherche par nom
    if search:
        df_search = df[df['Nom'].str.contains(search, case=False, na=False)]
        df_no_dates_search = df_no_dates[df_no_dates['Nom'].str.contains(search, case=False, na=False)]
        # Affichage détaillé si un seul résultat
        details = df_search.to_dict(orient='records')[0] if len(df_search) == 1 else None
        data = df_no_dates_search.to_dict(orient='records')
    else:
        data = df_no_dates.to_dict(orient='records')
    # Colonnes à afficher : ID, Nom, Mail, Pourcentage d'achèvement
    columns = []
    if 'ID' in df_no_dates.columns:
        columns.append('ID')
    if 'Nom' in df_no_dates.columns:
        columns.append('Nom')
    # Ne pas inclure la colonne mail
    # Calcul du pourcentage d'achèvement par apprenant
    def percent_row(row):
        module_cols = [col for col in df_no_dates.columns if col.startswith('M')]
        total = len(module_cols)
        done = sum([1 for col in module_cols if row[col] == '✅'])
        return round((done / total) * 100, 1) if total > 0 else 0
    percent_list = [percent_row(row) for _, row in df_no_dates.iterrows()]
    df_no_dates['% Achèvement'] = percent_list
    columns.append('% Achèvement')

    # Recalcule le pourcentage pour le sous-ensemble filtré (data)
    if search:
        percent_search_list = [percent_row(row) for _, row in df_no_dates_search.iterrows()]
        for i, row in enumerate(data):
            row['% Achèvement'] = percent_search_list[i]
    else:
        for i, row in enumerate(data):
            row['% Achèvement'] = percent_list[i]
    # Variables pour le template moderne
    completed_count = int(stats['total_cours_termines'])
    not_completed_count = int(stats['total_cours_non_termines'])
    total_learners = int(stats['total_apprenants'])
    completion_rate = round((completed_count / total_learners) * 100, 1) if total_learners > 0 else 0
    # Convertit les pourcentages d'activité en float natif et les noms en str natif
    activity_completion = []
    for item in stats['module_percent']:
        if isinstance(item, tuple) and len(item) == 2:
            col, percent = item
            activity_completion.append((str(col), float(percent)))
    module_names = [str(col) for col, _ in activity_completion]
    learners = data
    feedbacks = []  # À remplir si feedbacks disponibles
    from datetime import datetime
    current_year = datetime.now().year
    module_columns = [col for col in df_no_dates.columns if col.startswith('M')]
    return render_template(
        'dashboard.html',
        columns=columns,
        data=data,
        module_columns=module_columns,
        module_name_map=module_name_map,
        completed_count=completed_count,
        not_completed_count=not_completed_count,
        completion_rate=completion_rate,
        activity_completion=activity_completion,
        module_names=module_names,
        learners=learners,
        feedbacks=feedbacks,
        current_year=current_year,
        total_learners=total_learners,
        search=search,
        view=view,
        is_admin=is_admin,
        upload_message=upload_message,
        no_data=False
    )

if __name__ == '__main__':
    app.run(debug=True)
