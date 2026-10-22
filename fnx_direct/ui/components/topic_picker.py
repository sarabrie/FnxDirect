"""Topic tiles above the chat and the suggested starter questions for the chosen topic."""
import streamlit as st

from fnx_direct.knowledge.topics import DEFAULT_SUGGESTIONS, TOPICS

TOPIC_KEY = "topic"


def _toggle_topic(topic):
    st.session_state[TOPIC_KEY] = None if st.session_state.get(TOPIC_KEY) == topic else topic


def render_topic_picker():
    """
    Equal square tiles (icon above label). Clicking a tile limits the search to that topic;
    clicking it again clears the choice. Returns the topic key, or None for all topics.
    """
    selected = st.session_state.get(TOPIC_KEY)
    with st.container(key="topic_grid"):
        for column, (topic, info) in zip(st.columns(len(TOPICS), gap="small"), TOPICS.items()):
            with column:
                st.button(
                    info["label"],
                    icon=info["icon"],
                    key=f"topic_{topic}",
                    type="primary" if topic == selected else "secondary",
                    use_container_width=True,
                    on_click=_toggle_topic,
                    args=(topic,),
                )
    return selected


def render_suggestions(topic=None, disabled=False):
    """Starter questions for an empty conversation. Returns the clicked question or None."""
    suggestions = TOPICS[topic]["suggestions"] if topic in TOPICS else DEFAULT_SUGGESTIONS
    st.markdown('<div class="section-label">שאלות נפוצות</div>', unsafe_allow_html=True)
    selected_question = None
    with st.container(key="suggestions"):
        for column, suggestion in zip(st.columns(len(suggestions), gap="small"), suggestions):
            if column.button(
                suggestion, icon=":material/arrow_back:", use_container_width=True, disabled=disabled,
                key=f"suggestion_{suggestion}",
            ):
                selected_question = suggestion
    return selected_question
