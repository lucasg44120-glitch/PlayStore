# Play Store maison (Flask)

Un vrai store d'applications : l'admin envoie les `.exe` (icône, captures, description),
les visiteurs les téléchargent et les installent depuis le site.

## Lancer

**Windows** : double-clique sur `start.bat`
**Linux / macOS** : `./start.sh`

Puis ouvre http://localhost:8000
Depuis un autre PC du réseau : `http://IP-DU-SERVEUR:8000` (autorise le port 8000 dans le pare-feu).

## Configuration (`config.py`)

| Réglage | Défaut | Rôle |
|---|---|---|
| `ADMIN_USER` / `ADMIN_PASSWORD` | admin / admin123 | **À changer !** (ou variables d'environnement `STORE_ADMIN_USER`, `STORE_ADMIN_PASSWORD`) |
| `PORT` | 8000 | port du site |
| `MAX_UPLOAD_MB` | 500 | taille max d'un fichier |

## Utilisation

1. Clique sur le rond en haut à droite → connecte-toi avec le compte admin.
2. Onglet **Admin** → **Ajouter** : icône, nom, description, captures et le fichier d'installation (.exe, .msi, .zip, .apk…).
3. Les visiteurs ouvrent la fiche → **Installer** : le vrai `.exe` est téléchargé (avec choix de l'emplacement sur Chrome/Edge), puis il suffit de le lancer.

## Données

Tout est dans le dossier `data/` (base SQLite + fichiers). Sauvegarde ce dossier pour sauvegarder le store.

## Mettre en ligne (Internet)

- Passe derrière HTTPS avec un reverse proxy (Caddy, nginx…). Avec nginx, ajoute `client_max_body_size 600m;`.
- Change le mot de passe admin dans `config.py`.

## Limites

Un site web ne peut pas lancer un `.exe` tout seul : le navigateur télécharge le fichier, l'utilisateur le lance (Windows peut afficher SmartScreen pour un exe non signé).
