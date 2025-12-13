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
          <p style="margin:6px 0 0 0;">1) Выберите встречу Kontur Talk или загрузите файл. 2) Получите транскрипт, саммари и TODO. 3) Копируйте или
          скачивайте .txt.</p>
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


def list_zoom_recordings() -> List[Dict[str, Any]]:
    try:
        resp = client().get("/api/v1/zoom/recordings")
        resp.raise_for_status()
        return resp.json().get("recordings", [])
    except Exception as exc:
        st.error(f"Не удалось получить записи Zoom: {exc}")
        return []


def process_zoom_recording(rec: Dict[str, Any]) -> Optional[str]:
    try:
        payload = {
            "download_url": rec.get("download_url"),
            "file_extension": rec.get("file_extension"),
            "topic": rec.get("topic"),
            "duration_seconds": rec.get("duration_seconds"),
            "meeting_id": rec.get("meeting_id"),
        }
        resp = client().post(
            f"/api/v1/zoom/recordings/{rec.get('id')}/process",
            json=payload,
        )
        if resp.status_code >= 400:
            st.error(resp.json().get("detail", "Ошибка запуска обработки Zoom"))
            return None
        return resp.json().get("task_id")
    except Exception as exc:
        st.error(f"Ошибка запроса к Zoom: {exc}")
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
    source = st.radio(
        "Источник",
        ["Контур Talk", "Zoom", "Загрузка файла"],
        horizontal=True,
    )
    task_id: Optional[str] = None

    if source == "Контур Talk":
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

    elif source == "Zoom":
        with st.spinner("Получаю записи Zoom..."):
            recordings = list_zoom_recordings()
        if recordings:
            labels = []
            by_label = {}
            for idx, r in enumerate(recordings, start=1):
                topic = r.get("topic") or "Zoom запись"
                dur = r.get("duration_seconds") or 0
                start_time = r.get("recording_start") or ""
                label = f"{idx}. {topic} · {int(dur // 60)}m · {start_time}"
                labels.append(label)
                by_label[label] = r
            choice = st.selectbox("Запись", labels)
            if st.button("🚀 Обработать Zoom-запись"):
                task_id = process_zoom_recording(by_label[choice])
                if task_id:
                    st.success("Запрос отправлен. Ожидаем готовности результата.")
        else:
            st.info("Нет доступных записей Zoom.")

    else:
        uploaded = st.file_uploader(
            "Загрузите аудио/видео",
            type=["mp3", "wav", "ogg", "m4a", "mp4", "mkv", "webm"],
        )
        lang = st.selectbox("Язык", ["auto", "ru", "en"], index=0)
        if st.button("📤 Отправить файл", disabled=uploaded is None):
            if uploaded:
                with st.spinner("Отправка файла..."):
                    task_id = upload_file(uploaded, lang)
                    if task_id:
                        st.success("Файл отправлен. Ожидаем готовности результата.")
    return task_id


def parse_summary_block(data: Dict[str, Any]) -> Dict[str, Any]:
    """Нормализуем summary/key_points/action_items, убираем сырые JSON-блоки."""
    summary_raw = data.get("summary") or ""
    key_points = data.get("key_points") or []
    action_items = data.get("action_items") or []

    cleaned = summary_raw.strip()
    # Убираем ограждающие ```json ... ```
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    summary_val = summary_raw
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            summary_val = parsed.get("summary") or summary_val
            key_points = parsed.get("key_points") or key_points
            action_items = parsed.get("action_items") or action_items
    except Exception:
        pass

    def _clean_list(values: List[Any]) -> List[str]:
        result: List[str] = []
        for v in values:
            if v is None:
                continue
            s = str(v).strip().strip('"').strip()
            if s:
                result.append(s)
        return result

    return {
        "summary": (summary_val or "").strip(),
        "key_points": _clean_list(key_points),
        "action_items": _clean_list(action_items),
    }


def layout_results(task_id: Optional[str]) -> None:
    st.markdown("### Результаты")
    if "result_cache" not in st.session_state:
        st.session_state["result_cache"] = {}
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
        st.info("Задача в обработке. Обновите статус вручную при ожидании.")
        if st.button("🔄 Обновить статус", key=f"refresh-{task_id}"):
            st.rerun()
        return

    if st_status == "failed":
        st.error("Извините, сервис пока не работает (ошибка обработки).")
        return

    data = st.session_state["result_cache"].get(task_id)
    if not data:
        with st.spinner("Получаю результат..."):
            data = load_result(task_id)
        if data:
            st.session_state["result_cache"][task_id] = data

    if not data:
        return

    parsed = parse_summary_block(data)
    summary_val = parsed["summary"]
    key_points = parsed["key_points"]
    action_items = parsed["action_items"]

    tabs = st.tabs(["Транскрипция", "Саммари", "TODO / Action items"])
    with tabs[0]:
        transcript = data.get("transcription", "") or ""
        st.subheader("Полный текст транскрипции")
        st.download_button(
            "⬇️ Скачать .txt",
            data=transcript,
            file_name=f"{task_id}-transcript.txt",
            mime="text/plain",
            key=f"dl-transcript-{task_id}",
        )
        st.text_area("", transcript, height=260, key=f"ta-{task_id}-transcript")
    with tabs[1]:
        summary_md = f"**Summary:** {summary_val}"
        if key_points:
            bullets = "\n".join(f"- {kp}" for kp in key_points)
            summary_md += f"\n\n**Ключевые пункты:**\n{bullets}"
        st.markdown(summary_md)
        summary_text = f"Summary: {summary_val}"
        if key_points:
            summary_text += "\n\nКлючевые пункты:\n" + "\n".join(f"- {kp}" for kp in key_points)
        st.download_button(
            "⬇️ Скачать .txt",
            data=summary_text,
            file_name=f"{task_id}-summary.txt",
            mime="text/plain",
            key=f"dl-summary-{task_id}",
        )
    with tabs[2]:
        items = action_items or []
        todo_text = (
            "\n".join(f"- [ ] {item}" for item in items)
            if items
            else "Нет action items"
        )
        st.subheader("TODO / Action items")
        st.download_button(
            "⬇️ Скачать .txt",
            data=todo_text,
            file_name=f"{task_id}-todo.txt",
            mime="text/plain",
            key=f"dl-todo-{task_id}",
        )
        st.text_area("", todo_text, height=220, key=f"ta-{task_id}-todo")


def main() -> None:
    st.set_page_config(page_title="CallScribe UI", layout="wide")
    hero()
    if "last_task_id" not in st.session_state:
        st.session_state["last_task_id"] = None

    swagger_url = f"{API_BASE_URL.rstrip('/')}/docs"
    st.markdown(
        f"""
        <div style="padding:8px 12px; background:#0f172a; border-radius:10px; display:inline-block;">
          <span style="margin-right:8px;">🔗</span>
          <strong>Swagger UI:</strong>
          <a href="{swagger_url}" target="_blank" style="color:#38bdf8;">{swagger_url}</a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    created_task = layout_creator()
    if created_task:
        st.session_state["last_task_id"] = created_task
    st.markdown("---")
    layout_results(st.session_state.get("last_task_id"))


if __name__ == "__main__":
    main()
