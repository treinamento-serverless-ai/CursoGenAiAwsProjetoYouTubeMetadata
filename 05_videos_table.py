try:
    import os
    import google_auth_oauthlib.flow
    import googleapiclient.discovery
    import pandas as pd
    from google.oauth2.credentials import Credentials
    from dotenv import load_dotenv
    from datetime import datetime
except ModuleNotFoundError as e:
    print(f"Erro: {e}")
    print("\nCrie e ative o ambiente virtual:")
    print("  python3 -m venv .venv")
    print("  source .venv/bin/activate  # No Windows: .venv\\Scripts\\activate")
    print("\nDepois instale as dependências:")
    print("  pip3 install -r requirements.txt")
    exit(1)

# Carregar variáveis do .env
load_dotenv()

# Configuração do .env
MAX_VIDEOS = int(os.getenv('YOUTUBE_MAX_VIDEOS', 30))
FILTER_DRAFTS_ONLY = os.getenv('YOUTUBE_FILTER_DRAFTS_ONLY', 'False').lower() == 'true'
FILTER_BY_DATE = os.getenv('YOUTUBE_FILTER_BY_DATE', 'False').lower() == 'true'
DATE_START = os.getenv('YOUTUBE_DATE_START', '2024-01-01')
DATE_END = os.getenv('YOUTUBE_DATE_END', '2024-12-31')
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

# Constantes do .env
DATA_FOLDER = os.getenv('DATA_FOLDER')
TABLE_NAME = os.getenv('YOUTUBE_VIDEOS_TABLE')

# Autenticação
TOKEN_FILE = "token_readonly.json"

try:
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=SCOPES)
    else:
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            "client_secret.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
except Exception as e:
    print("ERRO: Falha na autenticacao com a API do YouTube")
    print(f"Detalhes: {str(e)}")
    print("\nSolucoes possiveis:")
    print("1. Verifique se o arquivo 'client_secret.json' existe no diretorio atual")
    print("2. Se o erro for relacionado a token invalido, delete o arquivo 'token_readonly.json' e execute novamente")
    print("3. Verifique se as credenciais do Google Cloud Console estao configuradas corretamente")
    print("4. Confirme se a YouTube Data API v3 esta habilitada no seu projeto")
    exit(1)

# Obter playlist de uploads
channel_request = youtube.channels().list(part="contentDetails", mine=True)
channel_response = channel_request.execute()
uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

# Obter vídeos com paginação
videos_data = []
next_page_token = None
videos_collected = 0

while videos_collected < MAX_VIDEOS:
    page_size = 50
    
    videos_request = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads_playlist_id,
        maxResults=page_size,
        pageToken=next_page_token
    )
    videos_response = videos_request.execute()
    
    for item in videos_response["items"]:
        if videos_collected >= MAX_VIDEOS:
            break
            
        video_id = item["snippet"]["resourceId"]["videoId"]
        video_title = item["snippet"]["title"]
        published_at = item["snippet"]["publishedAt"]
        
        videos_data.append({
            "video_id": video_id,
            "video_title": video_title,
            "published_at": published_at,
            "material_link": "",
            "bibliography_references": ""
        })
        videos_collected += 1
    
    next_page_token = videos_response.get("nextPageToken")
    if not next_page_token:
        break

# Aplicar filtro de status (draft) se habilitado
if FILTER_DRAFTS_ONLY and videos_data:
    print("Filtrando apenas vídeos em rascunho...")
    video_ids = [v["video_id"] for v in videos_data]
    
    filtered_videos = []
    for i in range(0, len(video_ids), 50):
        batch_ids = video_ids[i:i+50]
        status_request = youtube.videos().list(
            part="status",
            id=",".join(batch_ids)
        )
        status_response = status_request.execute()
        
        for video in status_response["items"]:
            status = video["status"]
            is_private = status.get("privacyStatus") == "private"
            is_scheduled = status.get("publishAt") is not None
            
            if is_private and not is_scheduled:
                original_data = next(v for v in videos_data if v["video_id"] == video["id"])
                filtered_videos.append(original_data)
    
    videos_data = filtered_videos
    print(f"Vídeos em rascunho encontrados: {len(videos_data)}")

# Aplicar filtro de data se habilitado
if FILTER_BY_DATE and videos_data:
    print(f"Filtrando vídeos entre {DATE_START} e {DATE_END}...")
    date_start = datetime.fromisoformat(DATE_START)
    date_end = datetime.fromisoformat(DATE_END).replace(hour=23, minute=59, second=59)
    
    filtered_by_date = []
    for video in videos_data:
        video_date = datetime.fromisoformat(video["published_at"].replace("Z", "+00:00"))
        if date_start <= video_date <= date_end:
            filtered_by_date.append(video)
    
    videos_data = filtered_by_date
    print(f"Vídeos no range de datas: {len(videos_data)}")

# Criar DataFrame e ordenar por título
df = pd.DataFrame(videos_data)
if not df.empty:
    df = df.drop(columns=["published_at"])
    df = df.sort_values('video_title').reset_index(drop=True)

# Salvar CSV
os.makedirs(DATA_FOLDER, exist_ok=True)
csv_path = os.path.join(DATA_FOLDER, TABLE_NAME)
df.to_csv(csv_path, index=False)

print(f"CSV salvo em: {csv_path}")
print(f"Total de vídeos: {len(df)}")
