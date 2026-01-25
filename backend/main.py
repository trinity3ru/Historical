"""
API на FastAPI для анализа исторических объектов.
Шаг 2: добавлен эндпоинт /analyze, валидация файла и вызов Gemini.
"""

import logging
import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types as genai_types
import httpx
import json
from pydantic import BaseModel, Field
from PIL import Image

# Загружаем переменные окружения из .env, чтобы не хранить ключ в коде.
# Загружаем переменные окружения из .env, чтобы не хранить ключ в коде.
load_dotenv()

GEMINI_API_KEY: Final[str | None] = os.getenv("GEMINI_API_KEY")
KIE_API_KEY: Final[str | None] = os.getenv("KIE_API_KEY")
KIE_CALLBACK_URL: Final[str | None] = os.getenv("KIE_CALLBACK_URL")
KIE_BASE_URL: Final[str] = "https://api.kie.ai/api/v1/jobs"
# Лимит сырого файла (до ресайза), чтобы не гонять огромные аплоады.
MAX_UPLOAD_SIZE: Final[int] = 8 * 1024 * 1024  # 8 MB
# Лимит после сжатия (итоговый размер, который отправляем в модель).
MAX_OUTPUT_SIZE: Final[int] = 1 * 1024 * 1024  # 1 MB
# Лимит по габаритам: уменьшаем до 1000px по длинной стороне.
MAX_DIMENSION: Final[int] = 1000
ALLOWED_TYPES: Final[set[str]] = {"image/png", "image/jpeg", "image/webp"}

# Создаём клиент Gemini один раз.
if GEMINI_API_KEY:
    genai_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    genai_client = None

# Хранилище задач генерации изображений (память процесса).
generation_store: dict[str, dict] = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("historical-backend")


class HealthResponse(BaseModel):
    status: str
    has_api_key: bool


class EventInfo(BaseModel):
    title: str = Field(..., description="Название события (английский)")
    title_ru: str = Field(..., description="Название события (русский)")
    date: str = Field(..., description="Дата или период события")
    description: str = Field(..., description="Краткое описание (английский)")
    description_ru: str = Field(..., description="Краткое описание (русский)")


class HistoricalObject(BaseModel):
    objectName: str = Field(..., description="Название объекта")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность 0-1")
    description: str = Field(..., description="Краткое описание на английском")
    description_ru: str = Field(..., description="Краткое описание на русском")
    events: list[EventInfo] | None = Field(
        default=None,
        description="Связанные исторические события с датами",
    )


class AnalyzeResponse(BaseModel):
    objects: list[HistoricalObject]


class KieCreateTaskResponse(BaseModel):
    taskId: str


class KieStatusResponse(BaseModel):
    taskId: str
    state: str
    resultUrls: list[str] | None = None
    failMsg: str | None = None


app = FastAPI(
    title="Historical Object Finder API",
    description="API для анализа изображений с помощью Gemini",
    version="0.2.0",
)

# Разрешаем CORS, чтобы фронтенд мог обращаться к API с другого домена/порта.
# Для учебного проекта allow_origins="*" допустимо, в проде лучше перечислять домены.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """
    Простой health-check.
    Отдельно показываем, видит ли процесс переменную GEMINI_API_KEY,
    чтобы удобнее диагностировать окружение.
    """
    return HealthResponse(status="ok", has_api_key=bool(GEMINI_API_KEY))


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_image(file: UploadFile = File(...)) -> AnalyzeResponse:
    """
    Принимает изображение, валидирует, вызывает Gemini и возвращает список объектов.
    """
    if genai_client is None:
        logger.error("GEMINI_API_KEY is not set")
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY не задан")

    if file.content_type not in ALLOWED_TYPES:
        logger.warning("Unsupported content type: %s", file.content_type)
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый тип файла: {file.content_type}",
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        logger.warning("Empty file received")
        raise HTTPException(status_code=400, detail="Файл пустой")
    if len(raw_bytes) > MAX_UPLOAD_SIZE:
        logger.warning("Upload too large: %s bytes", len(raw_bytes))
        raise HTTPException(status_code=400, detail="Файл слишком большой (лимит 8MB)")

    # Пробуем нормализовать изображение через Pillow, уменьшая до 1000px по длинной стороне
    # и перекодируя в JPEG с умеренным качеством, чтобы избежать таймаутов.
    try:
        with Image.open(BytesIO(raw_bytes)) as img:
            rgb_img = img.convert("RGB")
            w, h = rgb_img.size
            scale = 1.0
            resized = False
            if max(w, h) > MAX_DIMENSION:
                scale = MAX_DIMENSION / float(max(w, h))
                new_size = (int(w * scale), int(h * scale))
                rgb_img = rgb_img.resize(new_size, Image.LANCZOS)
                resized = True
            buf = BytesIO()
            rgb_img.save(buf, format="JPEG", quality=85, optimize=True)
            normalized_bytes = buf.getvalue()
            normalized_mime = "image/jpeg"
            logger.info(
                "Image normalized: orig_size=%s normalized_size=%s mode=%s format=%s scale=%.3f resized=%s",
                len(raw_bytes),
                len(normalized_bytes),
                img.mode,
                img.format,
                scale,
                resized,
            )
            if len(normalized_bytes) > MAX_OUTPUT_SIZE:
                logger.warning(
                    "Normalized image too large after compression: %s bytes",
                    len(normalized_bytes),
                )
                raise HTTPException(
                    status_code=400,
                    detail="Файл слишком большой после сжатия (лимит 1MB)",
                )
    except HTTPException:
        raise
    except Exception as pillow_err:  # noqa: BLE001
        logger.exception("Pillow failed to process image")
        raise HTTPException(
            status_code=400,
            detail=f"Не удалось обработать изображение (Pillow): {pillow_err}",
        ) from pillow_err

    # Временное сохранение на диск (учебная демонстрация) и базовая очистка.
    suffix = Path(file.filename or "").suffix or ".img"
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(normalized_bytes)
            tmp_path = tmp.name

        prompt = (
            "Analyze the image to identify historical objects or landmarks. "
            "For each object found, return JSON with fields: "
            "objectName (string), confidence (0-1), description (EN), description_ru (RU). "
            "Additionally, provide up to 3 related historical events with dates: "
            "events: [{title (EN), title_ru (RU), date, description (EN), description_ru (RU)}]. "
            "If no objects are found, return an empty array."
        )

        image_part = genai_types.Part.from_bytes(
            data=normalized_bytes, mime_type=normalized_mime
        )
        text_part = genai_types.Part.from_text(prompt)

        # Описываем схему, которую просим у модели.
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "objectName": {"type": "string"},
                    "confidence": {"type": "number"},
                    "description": {"type": "string"},
                    "description_ru": {"type": "string"},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "title_ru": {"type": "string"},
                                "date": {"type": "string"},
                                "description": {"type": "string"},
                                "description_ru": {"type": "string"},
                            },
                            "required": ["title", "title_ru", "date", "description", "description_ru"],
                        },
                    },
                },
                "required": ["objectName", "confidence", "description", "description_ru"],
            },
        }

        response = genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {
                    "role": "user",
                    "parts": [image_part, text_part],
                }
            ],
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )

        text = (response.text or "").strip()
        logger.info(
            "Gemini response length=%s status=%s",
            len(text),
            getattr(response, "prompt_feedback", None),
        )
        if not text:
            return AnalyzeResponse(objects=[])

        try:
            import json

            parsed = json.loads(text)
        except Exception as parse_err:  # noqa: BLE001
            # Документируем ошибку, чтобы в UI можно было подсказать пользователю.
            raise HTTPException(
                status_code=502,
                detail=f"Не удалось разобрать ответ модели как JSON: {parse_err}",
            ) from parse_err

        objects: list[HistoricalObject] = []
        if isinstance(parsed, list):
            for item in parsed:
                try:
                    objects.append(HistoricalObject(**item))
                except Exception:
                    # Пропускаем некорректные элементы, оставшиеся вернём.
                    logger.warning("Skip invalid item from model response: %s", item)
                    continue

        return AnalyzeResponse(objects=objects)

    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        # Логируем сжатое описание ошибки для диагностики.
        logger.exception("Unexpected error during analysis")
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {err}") from err
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                # Если файл не удалился, просто продолжаем; на учебном проекте допустимо.
                logger.warning("Failed to delete temp file: %s", tmp_path)
                pass


def build_prompt_for_event(event: EventInfo) -> str:
    return (
        f"Create a historically accurate illustration for the event '{event.title}' "
        f"({event.title_ru}), date {event.date}. "
        f"Context EN: {event.description}. "
        f"Context RU: {event.description_ru}. "
        "Style: realistic, balanced lighting, focus on key people/architecture relevant to the event. "
        "Do not add text on the image."
    )


def normalize_kie_state(raw_state: str | None) -> str:
    """
    Нормализуем статус KIE к одному из: waiting/success/fail.
    Это нужно, потому что API может возвращать разные слова (succeeded/failed/etc).
    """
    if not raw_state:
        return "waiting"
    state_lower = raw_state.lower()
    if state_lower in {"success", "succeeded", "done", "completed"}:
        return "success"
    if state_lower in {"fail", "failed", "error"}:
        return "fail"
    return "waiting"


def normalize_result_urls(value) -> list[str] | None:
    """
    Приводим resultUrls к списку строк.
    KIE может вернуть список строк или список объектов с полем url.
    """
    if value is None:
        return None
    urls: list[str] = []
    if isinstance(value, str):
        urls = [value]
    elif isinstance(value, dict):
        candidate = value.get("url") or value.get("imageUrl")
        if isinstance(candidate, str):
            urls = [candidate]
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict):
                candidate = item.get("url") or item.get("imageUrl")
                if isinstance(candidate, str):
                    urls.append(candidate)
    # Чистим пустые строки и мусор.
    urls = [u for u in urls if isinstance(u, str) and u.strip()]
    return urls or None


@app.post("/generate-image", response_model=KieCreateTaskResponse)
async def generate_image(event: EventInfo):
    """
    Создать задачу генерации изображения через kie.ai (nano-banana-pro).
    """
    if not KIE_API_KEY:
        raise HTTPException(status_code=500, detail="KIE_API_KEY не задан")

    payload = {
        "model": "nano-banana-pro",
        "input": {
            "prompt": build_prompt_for_event(event),
            "image_input": [],
            "aspect_ratio": "1:1",
            "resolution": "1K",
            "output_format": "png",
        },
    }
    if KIE_CALLBACK_URL:
        payload["callBackUrl"] = KIE_CALLBACK_URL

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(f"{KIE_BASE_URL}/createTask", json=payload, headers=headers)
        except httpx.HTTPError as err:
            logger.exception("KIE createTask request failed")
            raise HTTPException(status_code=502, detail=f"KIE API недоступен: {err}") from err

    if resp.status_code != 200:
        logger.warning("KIE createTask error: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail="KIE API вернул ошибку при создании задачи")

    # Важно: KIE иногда может вернуть пустой/некорректный JSON.
    try:
        data = resp.json()
    except ValueError as parse_err:
        logger.warning("KIE createTask returned invalid JSON: %s", resp.text)
        raise HTTPException(
            status_code=502,
            detail=f"KIE API вернул некорректный JSON: {parse_err}",
        ) from parse_err
    if not isinstance(data, dict):
        logger.warning("KIE createTask unexpected payload: %s", data)
        raise HTTPException(status_code=502, detail="KIE API вернул некорректный ответ")

    data_payload = data.get("data")
    if not isinstance(data_payload, dict):
        logger.warning("KIE createTask missing data field: %s", data)
        raise HTTPException(status_code=502, detail="KIE API не вернул поле data")

    task_id = data_payload.get("taskId")
    if not task_id:
        raise HTTPException(status_code=502, detail="KIE API не вернул taskId")

    generation_store[task_id] = {
        "state": "waiting",
        "resultUrls": None,
        "failMsg": None,
        "event": event.model_dump(),
    }
    return KieCreateTaskResponse(taskId=task_id)


@app.get("/generation-status", response_model=KieStatusResponse)
async def generation_status(taskId: str):
    """
    Получить статус задачи генерации. Если задача ещё не завершена, опрашиваем KIE,
    чтобы клиент не застревал в состоянии waiting.
    """
    entry = generation_store.get(taskId)
    if entry and entry.get("state") in {"success", "fail"}:
        return KieStatusResponse(
            taskId=taskId,
            state=entry.get("state") or "waiting",
            resultUrls=entry.get("resultUrls"),
            failMsg=entry.get("failMsg"),
        )

    if not KIE_API_KEY:
        raise HTTPException(status_code=500, detail="KIE_API_KEY не задан")

    headers = {"Authorization": f"Bearer {KIE_API_KEY}"}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(f"{KIE_BASE_URL}/recordInfo", params={"taskId": taskId}, headers=headers)
        except httpx.HTTPError as err:
            logger.exception("KIE recordInfo request failed")
            raise HTTPException(status_code=502, detail=f"KIE API недоступен: {err}") from err

    if resp.status_code != 200:
        logger.warning("KIE recordInfo error: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail="KIE API вернул ошибку при получении статуса")

    # Аналогично, защищаемся от пустого/некорректного JSON.
    try:
        data = resp.json()
    except ValueError as parse_err:
        logger.warning("KIE recordInfo returned invalid JSON: %s", resp.text)
        raise HTTPException(
            status_code=502,
            detail=f"KIE API вернул некорректный JSON: {parse_err}",
        ) from parse_err
    if not isinstance(data, dict):
        logger.warning("KIE recordInfo unexpected payload: %s", data)
        raise HTTPException(status_code=502, detail="KIE API вернул некорректный ответ")

    data_payload = data.get("data")
    if not isinstance(data_payload, dict):
        logger.warning("KIE recordInfo missing data field: %s", data)
        raise HTTPException(status_code=502, detail="KIE API не вернул поле data")

    state_raw = data_payload.get("state", "waiting")
    state = normalize_kie_state(state_raw)
    result_urls: list[str] | None = None
    fail_msg = data_payload.get("failMsg")
    try:
        result_json = data_payload.get("resultJson")
        parsed = None
        if isinstance(result_json, str) and result_json:
            parsed = json.loads(result_json)
        elif isinstance(result_json, dict):
            parsed = result_json
        if isinstance(parsed, dict):
            result_urls = normalize_result_urls(
                parsed.get("resultUrls")
                or parsed.get("resultUrl")
                or parsed.get("imageUrl")
                or parsed.get("images")
            )
    except Exception:
        pass

    # Логируем детали статуса, чтобы проще разбираться с зависаниями.
    logger.info(
        "KIE status: taskId=%s state_raw=%s state=%s has_urls=%s failMsg=%s",
        taskId,
        state_raw,
        state,
        bool(result_urls),
        fail_msg,
    )

    generation_store[taskId] = {
        "state": state,
        "resultUrls": result_urls,
        "failMsg": fail_msg,
        "event": entry.get("event") if entry else None,
    }

    return KieStatusResponse(
        taskId=taskId,
        state=state,
        resultUrls=result_urls,
        failMsg=fail_msg,
    )


@app.post("/kie-callback")
async def kie_callback(payload: dict):
    """
    Приём callback от KIE (если задан callBackUrl).
    """
    task_id = payload.get("data", {}).get("taskId")
    if not task_id:
        raise HTTPException(status_code=400, detail="Нет taskId в callback")

    state = payload.get("data", {}).get("state", "waiting")
    fail_msg = payload.get("data", {}).get("failMsg")
    result_urls = None
    try:
        result_json = payload.get("data", {}).get("resultJson")
        parsed = None
        if isinstance(result_json, str) and result_json:
            parsed = json.loads(result_json)
        elif isinstance(result_json, dict):
            parsed = result_json
        if isinstance(parsed, dict):
            result_urls = normalize_result_urls(
                parsed.get("resultUrls")
                or parsed.get("resultUrl")
                or parsed.get("imageUrl")
                or parsed.get("images")
            )
    except Exception:
        logger.warning("Failed to parse resultJson in callback for task %s", task_id)

    generation_store[task_id] = {
        "state": state,
        "resultUrls": result_urls,
        "failMsg": fail_msg,
    }

    return {"ok": True}

