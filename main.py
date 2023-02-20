from requests import Session
from bs4 import BeautifulSoup
from zipfile import ZipFile
from difflib import get_close_matches
from dotenv import load_dotenv
from tqdm import tqdm
import genanki
import os
import shutil
import re
import promptlib


s = Session()

# recuperation des quizz
quizz_page = s.get('http://www.musique-orsay.fr/ressources-menu/quizz-musicaux/')
quizz_soup = BeautifulSoup(quizz_page.text, features='html.parser')
quizz = []
for p in quizz_soup.findAll('p', class_='has-text-align-center'):
    if len(p.findAll('a')):
        quizz.append({'name': p.a.text, 'url': p.a['href']})

# choix du quizz
for i, quiz in enumerate(quizz):
    print(i, '=>', quiz['name'])

quiz = quizz[int(input('Selectionnez le quiz que vous voulez apprendre '))]
print()

# recuperation des titres des musiques et du lien des musiques courtes
html = s.get(quiz['url'])
soup = BeautifulSoup(html.text, features="html.parser")
music_names = []
music_links_all = []
for p in soup.findAll('p', class_=False, id=False):
    # cherche les liens
    mp3_links = p.findAll('a', href=lambda href: href and '.mp3' in href)
    if len(mp3_links):
        music_links = []
        for link in mp3_links:
            # recupere le lien
            music_links.append(link['href'])
            # retire le lien
            link.decompose()
        # formate le texte
        music_list = BeautifulSoup(str(p).replace('<br/>', '\n'), features="html.parser").text.replace(u'\xa0', u' ').split('\n')
        music_names.append(music_list)
        music_links_all.append(music_links)

# recuperation lien du fichier zip
links = []
for link in soup.findAll('a', href=lambda href: href and '.zip' in href):
    links.append(link['href'])

# choix de la partie du quizz si besoin
if len(links) > 1:
    choices = soup.findAll('p', string=re.compile(r'^\d* à \d*.*$'))
    for i, choice in enumerate(choices):
        print(i, '=>', choice.text)

    playlist = int(input('Selectionnez la partie du quiz que vous voulez apprendre '))
    print()
    choice = [word for word in choices[playlist].text.split() if word.isdigit()]
    choice = f'{choice[0]}-{choice[1]}'
else:
    playlist = 0

# creation du dossier temp
os.makedirs('temp', exist_ok=True)

# recuperation des variables env
if os.path.exists('.env'):
    load_dotenv()

# recuperation du nom d'utilisateur
username = os.environ.get('ID')
if not username:
    username = input("Entrez le Nom d'utilisateur ")

# recuperation du mot de passe
password = os.environ.get('PASSWORD')
if not password:
    password = input("Entrez le Mot de Passe ")

# recupere le zip
zip = s.get(links[playlist],
            auth=(username, password), allow_redirects=True, stream=True)

music_folder = 'temp/music'

# si le mdp est correct
if zip.status_code == 200:
    total = int(zip.headers.get('content-length', 0))
    # duivi du telechargement
    with open('temp/music.zip', 'wb') as file, tqdm(desc='Telechargement...', total=total, unit='B', unit_scale=True, unit_divisor=1024) as bar:
        for data in zip.iter_content(chunk_size=1024):
            size = file.write(data)
            bar.update(size)
    print()
    # extraction des musiques
    with ZipFile('temp/music.zip', 'r') as zip:
        for member in tqdm(zip.infolist(), desc='Extraction...'):
            zip.extract(member, music_folder)
        print()
#  si le mot de passe est incorrect
elif zip.status_code == 401:
    print("Nom d'utilisateur ou mot de passe incorrect")
    print('Telechargement des musiques courtes')

    # creation du dossier music
    os.makedirs(music_folder, exist_ok=True)
    # telechargement des musiques courtes
    for link in tqdm(music_links_all[playlist], desc='Telechargement...', unit='music'):
        mp3 = s.get(link, allow_redirects=True)
        title = link.split("/")[-1]
        open(f'{music_folder}/{title}', 'wb').write(mp3.content)
    print()
else:
    raise(Exception('Problème lors du telechargement des musiques'))

# liste le nom des fichiers musicauxs
music_files = [f for f in os.listdir(music_folder) if os.path.isfile(os.path.join(music_folder, f))]

# si les musiques ne sont pas dans le dossier music
if not music_files:
    music_folder = f"temp/music/{[f for f in os.listdir(music_folder) if f != '__MACOSX'][0]}"
    music_files = [f for f in os.listdir(music_folder) if os.path.isfile(os.path.join(music_folder, f))]

# si il y a moins de musiques que de titre
if len(music_files) < len(music_names[playlist]):
    raise(Exception('Moins de musique que de titre'))

print('Generation du fichier Anki...')
print()

# formate le nom du quiz
if playlist == 0:
    deck_name = f'{quiz["name"]}'
else:
    deck_name = f'{quiz["name"]} {choice}'
# creation du quiz
my_deck = genanki.Deck(name=deck_name)
files = []

for i, music in enumerate(music_names[playlist]):
    # enleve les dates apres un –
    regex = r"(?P<date>\– \d{4} *)"
    music = re.sub(regex, '', music, 0)
    # enleve les infos entre parentheses
    regex = r"(?P<parenthese>\([^\)]*\))"
    music = re.sub(regex, '', music, 0)
    # enleve les espaces inutiles
    regex = r"(?P<space> {2,})"
    music = re.sub(regex, ' ', music, 0)

    # association des fichiers avec les titres
    file = get_close_matches(music, music_files, n=1, cutoff=0)[0]
    music_files.remove(file)
    # ajourte le fichier et la note au deck
    files.append(f'{music_folder}/{file}')
    note = genanki.Note(model=genanki.BASIC_MODEL, fields=[f'[sound:{file}]', music], sort_field=i)
    my_deck.add_note(note)

# creation du package
my_package = genanki.Package(my_deck)
# ajout des fichiers au package
my_package.media_files = files
# formate le nom du fichier
file_name = f"{deck_name.lower().replace(' ', '_')}.apkg"
# demande le dossier d'exportation
path = promptlib.Files().dir()
# exporte le package
my_package.write_to_file(f'{path}\{file_name}')
print(f'{file_name} enregistré avec succès dans {path} !')

# supprime le dossier temp
if os.path.isdir('temp'):
    shutil.rmtree('temp')
