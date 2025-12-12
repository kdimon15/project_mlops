import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

import httpx
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


@lru_cache(maxsize=1)
def client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, timeout=20.0)


def copy_button(label: str, text: str) -> None:
    escaped = json.dumps(text)
    btn = f"""
    <button class="copy-btn" onclick='navigator.clipboard.writeText({escaped});'>
      📋 {label}
    </button>
    """
    st.markdown(btn, unsafe_allow_html=True)


def render_block(title: str, text: str, key_prefix: str) -> None:
    st.subheader(title)
    col1, col2 = st.columns([1, 2])
    with col1:
        copy_button("Копировать", text)
        st.download_button(
            "⬇️ Скачать .txt",
            data=text,
            file_name=f"{key_prefix}.txt",
            mime="text/plain",
            key=f"dl-{key_prefix}",
        )
    with col2:
        st.caption("Можно копировать или скачать как txt.")
    st.text_area("", text, height=260, key=f"ta-{key_prefix}")


def hero() -> None:
    st.markdown(
        """
        <style>
        .hero {
            padding: 18px 20px;
            border-radius: 16px;
            background: linear-gradient(135deg, #0d6efd, #20c997);
            color: #fff;
            box-shadow: 0 12px 30px rgba(0,0,0,0.35);
            animation: glow 4s ease-in-out infinite;
        }
        @keyframes glow {
          0% { box-shadow: 0 12px 30px rgba(0,0,0,0.35); }
          50% { box-shadow: 0 12px 30px rgba(0,0,0,0.55); }
          100% { box-shadow: 0 12px 30px rgba(0,0,0,0.35); }
        }
        .copy-btn {
            background: #0d6efd;
            color: #fff;
            border: none;
            padding: 6px 10px;
            border-radius: 8px;
            cursor: pointer;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
            margin-right: 6px;
            margin-bottom: 8px;
        }
        .copy-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 14px rgba(0,0,0,0.2);
        }
        .status-chip {
            display: inline-block;
            padding: 6px 10px;
            border-radius: 10px;
            font-weight: 600;
        }
        .status-queued { background: #113152; color: #8cc2ff; }
        .status-processing { background: #2f2a00; color: #ffd666; }
        .status-completed { background: #0f3a1a; color: #8be6a2; }
        .status-failed { background: #3a0f0f; color: #ffb3b3; }
        </style>
        <div class="hero">
          <h2>CallScribe UI</h2>
          <p style="margin:6px 0 0 0;">1) Выберите встречу Kontur Talk или загрузите файл. 2) Получите транскрипт, саммари и TODO. 3) Копируйте или скачивайте .txt.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def list_recordings(limit: int = 50) -> List[Dict[str, Any]]:
    try:
        resp = client().get("/api/v1/kontur-talk/recordings", params={"limit": limit})
        resp.raise_for_status()
        return resp.json().get("recordings", [])
    except Exception as exc:
        st.error(f"Не удалось получить список записей: {exc}")
        return []


def process_recording(recording_id: str) -> Optional[str]:
    try:
        resp = client().post(f"/api/v1/kontur-talk/recordings/{recording_id}/process")
        if resp.status_code >= 400:
            st.error(resp.json().get("detail", "Ошибка запуска обработки"))
            return None
        return resp.json().get("task_id")
    except Exception as exc:
        st.error(f"Ошибка запроса: {exc}")
        return None


def upload_file(file, language: str) -> Optional[str]:
    try:
        files = {"file": (file.name, file, file.type or "application/octet-stream")}
        data = {"language": language}
        resp = client().post("/api/v1/transcribe", files=files, data=data)
        if resp.status_code >= 400:
            st.error(resp.json().get("detail", "Ошибка загрузки"))
            return None
        return resp.json().get("task_id")
    except Exception as exc:
        st.error(f"Ошибка загрузки: {exc}")
        return None


def load_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Получить статус задачи."""
    try:
        resp = client().get(f"/api/v1/tasks/{task_id}")
        if resp.status_code >= 400:
            return None
        return resp.json()
    except Exception:
        return None


def load_result(task_id: str) -> Optional[Dict[str, Any]]:
    try:
        resp = client().get(f"/api/v1/results/{task_id}")
        if resp.status_code >= 400:
            st.warning(resp.json().get("detail", "Задача не готова"))
            return None
        return resp.json()
    except Exception as exc:
        st.error(f"Ошибка запроса результата: {exc}")
        return None


def layout_creator() -> Optional[str]:
    st.markdown("### Создать задачу")
    tabs = st.tabs(["Выбрать встречу Kontur Talk", "Загрузить файл"])
    task_id: Optional[str] = None

    with tabs[0]:
        with st.spinner("Получаю список встреч..."):
            recordings = list_recordings()
        if recordings:
            options = {}
            labels = []
            for idx, r in enumerate(recordings, start=1):
                title = r.get("title") or "Встреча без названия"
                dur = r.get("duration")
                dur_txt = f"{int(dur)}s" if dur is not None else "—"
                label = f"{idx}. {title} · {dur_txt}"
                labels.append(label)
                options[label] = r["recording_id"]
            choice = st.selectbox("Встреча", labels)
            if st.button("🚀 Обработать встречу"):
                task_id = process_recording(options[choice])
                if task_id:
                    st.success("Запрос отправлен. Ожидаем готовности результата.")
        else:
            st.info("Нет доступных записей.")

    with tabs[1]:
        uploaded = st.file_uploader("Загрузите аудио/видео", type=["mp3", "wav", "ogg", "m4a", "mp4", "mkv", "webm"])
        lang = st.selectbox("Язык", ["auto", "ru", "en"], index=0)
        if st.button("📤 Отправить файл", disabled=uploaded is None):
            if uploaded:
                with st.spinner("Отправка файла..."):
                    task_id = upload_file(uploaded, lang)
                    if task_id:
                        st.success("Файл отправлен. Ожидаем готовности результата.")
    return task_id


def layout_results(task_id: Optional[str]) -> None:
    st.markdown("### Результаты")
    if not task_id:
        st.info("Создайте задачу через встречу или загрузку файла.")
        return

    status = load_status(task_id)
    if not status:
        st.error("Извините, сервис пока не работает (нет статуса).")
        return

    st_status = status.get("status")
    badge_class = {
        "queued": "status-queued",
        "processing": "status-processing",
        "completed": "status-completed",
        "failed": "status-failed",
    }.get(st_status, "status-queued")
    st.markdown(
        f"Статус: <span class='status-chip {badge_class}'>{st_status}</span>",
        unsafe_allow_html=True,
    )

    if st_status in ("queued", "processing"):
        st.info("Задача в обработке. Страница обновится автоматически.")
        # Автообновление страницы каждые 5 секунд, пока задача не завершена
        st.markdown(
            "<meta http-equiv='refresh' content='5'>",
            unsafe_allow_html=True,
        )
        return

    if st_status == "failed":
        st.error("Извините, сервис пока не работает (ошибка обработки).")
        return

    with st.spinner("Получаю результат..."):
        data = load_result(task_id)

    if not data:
        return

    tabs = st.tabs(["Транскрипция", "Саммари", "TODO / Action items"])
    with tabs[0]:
        render_block("Полный текст транскрипции", data.get("transcription", ""), f"{task_id}-transcript")
    with tabs[1]:
        render_block("Саммари", data.get("summary", ""), f"{task_id}-summary")
    with tabs[2]:
        items = data.get("action_items") or []
        todo_text = "\n".join(f"- [ ] {item}" for item in items) if items else "Нет action items"
        render_block("TODO / Action items", todo_text, f"{task_id}-todo")


def main() -> None:
    st.set_page_config(page_title="CallScribe UI", layout="wide")
    hero()

    st.markdown("---")
    created_task = layout_creator()
    if created_task:
        st.session_state["last_task_id"] = created_task
    st.markdown("---")
    layout_results(st.session_state.get("last_task_id"))


if __name__ == "__main__":
    main()

