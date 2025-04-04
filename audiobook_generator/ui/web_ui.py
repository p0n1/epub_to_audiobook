import datetime
from multiprocessing import Process
from pathlib import Path
from tkinter import Tk, filedialog
from typing import Optional

import gradio as gr

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.tts_providers.azure_tts_provider import get_azure_supported_languages, \
    get_azure_supported_voices, get_azure_supported_output_formats
from audiobook_generator.tts_providers.edge_tts_provider import get_edge_tts_supported_voices, \
    get_edge_tts_supported_language, get_edge_tts_supported_output_formats
from audiobook_generator.tts_providers.openai_tts_provider import get_openai_supported_models, \
    get_openai_supported_voices, get_openai_instructions_example, get_openai_supported_output_formats
from audiobook_generator.tts_providers.piper_tts_provider import get_piper_supported_languages, \
    get_piper_supported_voices, get_piper_supported_qualities, get_piper_supported_speakers
from audiobook_generator.utils.log_handler import red_log_file
from main import main

selected_tts = "OpenAI"
running_process: Optional[Process] = None
log_file = None
delayed_log_read_counter = 0

def get_folder_path():
    root = Tk()
    root.withdraw()
    output_dir = filedialog.askdirectory()
    return output_dir

def get_file_path(custom_type_limitation: tuple):
    root = Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(filetypes=(custom_type_limitation, ("All files", "*.*")))
    return file_path

def on_tab_change(evt: gr.SelectData):
    print(f"{evt.value} tab selected")
    global selected_tts
    selected_tts = evt.value

def get_azure_voices_by_language(language):
    voices_list = [voice for voice in get_azure_supported_voices() if voice.startswith(language)]
    return gr.Dropdown(voices_list, value=voices_list[0], label="Voice", interactive=True, info="Select the voice")

def get_edge_voices_by_language(language):
    voices_list = [voice for voice in get_edge_tts_supported_voices() if voice.startswith(language)]
    return gr.Dropdown(voices_list, value=voices_list[0], label="Voice", interactive=True, info="Select the voice")

def get_piper_supported_voices_gui(language):
    voices_list = get_piper_supported_voices(language)
    return gr.Dropdown(voices_list, value=voices_list[0], label="Voice", interactive=True, info="Select the voice")

def get_piper_supported_qualities_gui(language, voice):
    qualities_list = get_piper_supported_qualities(language, voice)
    return gr.Dropdown(qualities_list, value=qualities_list[0], label="Quality", interactive=True, info="Select the quality")

def get_piper_supported_speakers_gui(language, voice, quality):
    speakers_list = get_piper_supported_speakers(language, voice, quality)
    return gr.Dropdown(speakers_list, value=speakers_list[0], label="Speaker", interactive=True, info="Select the speaker")


def process_ui_form(input_file, output_dir, worker_count, log_level, output_text, preview,
                    search_and_replace_file, title_mode, new_line_mode, chapter_start, chapter_end, remove_endnotes, remove_reference_numbers,
                    model, voices, speed, openai_output_format, instructions,
                    azure_language, azure_voice, azure_output_format, break_duration,
                    edge_language, edge_voice, edge_output_format, proxy, edge_voice_rate, edge_volume, edge_pitch,
                    piper_executable_path, piper_docker_image, piper_language, piper_voice, piper_quality, piper_speaker,
                    piper_noice_scale, piper_noice_w_scale, piper_length_scale, piper_sentence_silence):

    config = GeneralConfig(None)
    config.input_file = input_file
    config.output_folder = output_dir
    config.preview = preview
    config.output_text = output_text
    config.log = log_level
    config.worker_count = worker_count
    config.no_prompt = True

    config.title_mode = title_mode
    config.newline_mode = new_line_mode
    config.chapter_start = chapter_start
    config.chapter_end = chapter_end
    config.remove_endnotes = remove_endnotes
    config.remove_reference_numbers = remove_reference_numbers
    config.search_and_replace_file = search_and_replace_file

    global selected_tts
    if selected_tts == "OpenAI":
        config.tts = "openai"
        config.output_format = openai_output_format
        config.voice_name = voices
        config.model_name = model
        config.instructions = instructions
        config.speed = speed
    elif selected_tts == "Azure":
        config.tts = "azure"
        config.language = azure_language
        config.voice_name = azure_voice
        config.output_format = azure_output_format
        config.break_duration = break_duration
    elif selected_tts == "Edge":
        config.tts = "edge"
        config.language = edge_language
        config.voice_name = edge_voice
        config.output_format = edge_output_format
        config.proxy = proxy
        config.voice_rate = edge_voice_rate
        config.voice_volume = edge_volume
        config.voice_pitch = edge_pitch
    elif selected_tts == "Piper":
        config.tts = "piper"
        config.piper_path = piper_executable_path
        config.piper_docker_image = piper_docker_image
        config.model_name = f"{piper_language}-{piper_voice}-{piper_quality}"
        config.piper_speaker = piper_speaker
        config.piper_noise_scale = piper_noice_scale
        config.piper_noise_w_scale = piper_noice_w_scale
        config.piper_length_scale = piper_length_scale
        config.piper_sentence_silence = piper_sentence_silence
    else:
        raise ValueError("Unsupported TTS provider selected")

    launch_audiobook_generator(config)


def launch_audiobook_generator(config):
    global running_process
    if running_process and running_process.is_alive():
        return

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    global log_file
    log_file = Path(f"EtA_{timestamp}.log")
    log_file.touch()
    config.log_file = log_file

    running_process = Process(target=main, args=(config,log_file.absolute()))
    running_process.start()


def terminate_audiobook_generator():
    global running_process
    if running_process and running_process.is_alive():
        running_process.terminate()
        running_process = None

def read_logs(current_value):
    global delayed_log_read_counter
    global running_process
    global log_file
    if not running_process:
        return current_value

    if running_process.is_alive():
        return red_log_file(log_file)
    else:
        if delayed_log_read_counter < 5:
            delayed_log_read_counter += 1
            return red_log_file(log_file)
        return current_value


def host_ui(config):
    with gr.Blocks() as ui:
        with gr.Row(equal_height=True):
            with gr.Column():
                input_file = gr.Textbox(label="Select the book file to process", interactive=True)
                gr.Button("Browse").click(fn=lambda: get_file_path(("EPUB file", "*.epub")), outputs=input_file)

            with gr.Column():
                output_dir = gr.Textbox(label="Select Output Directory", placeholder="./audiobook_output",
                                        interactive=True)
                gr.Button("Browse").click(get_folder_path, outputs=output_dir)


            worker_count = gr.Slider(minimum=1, maximum=8, step=1, label="Worker Count", value=4,
                                     info="Number of workers to use for processing. More workers may speed up the process but will use more resources.")
            log_level = gr.Dropdown(["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"], label="Log Level",
                                    value="INFO", interactive=True)
            with gr.Column():
                output_text = gr.Checkbox(label="Enable Output Text", value=False,
                                      info="Export a plain text file for each chapter.")
                preview = gr.Checkbox(label="Enable Preview Mode", value=False,
                                  info="It will not convert the to audio, only prepare chapters and cost.")

        gr.Markdown("---")
        with gr.Row(equal_height=True):
            with gr.Column():
                search_and_replace_file = gr.Textbox(label="Select search and replace file", interactive=True)
                gr.Button("Browse").click(fn=lambda: get_file_path(("Text file", "*.txt")), outputs=input_file)

            title_mode = gr.Dropdown(["auto", "tag_text", "first_few"], label="Title Mode", value="auto",
                                     interactive=True, info="Choose the parse mode for chapter title.")
            new_line_mode = gr.Dropdown(["single", "double", "none"], label="New Line Mode", value="double",
                                 interactive=True, info="Choose the mode of detecting new paragraphs")
            chapter_start = gr.Slider(minimum=1, maximum=100, step=1, label="Chapter Start", value=1,
                                      interactive=True, info="Select chapter start index (default: 1)")
            chapter_end = gr.Slider(minimum=-1, maximum=100, step=1, label="Chapter End", value=-1,
                                    interactive=True, info="Chapter end index (default: -1, means last chapter)")
            with gr.Column():
                remove_endnotes = gr.Checkbox(label="Remove Endnotes", value=True, info="Remove endnotes from text")

                remove_reference_numbers = gr.Checkbox(label="Remove Reference Numbers", value=True,
                                                       info="Remove reference numbers from text")


        gr.Markdown("---")
        with gr.Tabs():
            with gr.Tab("OpenAI") as open_ai_tab:
                gr.Markdown("It is expected that user configured: `OPENAI_API_KEY` in the environment variables. Optionally `OPENAI_API_BASE` can be set to overwrite OpenAI API endpoint.")
                with gr.Row(equal_height=True):
                    model = gr.Dropdown(get_openai_supported_models(), label="Model", interactive=True, allow_custom_value=True)
                    voices = gr.Dropdown(get_openai_supported_voices(), label="Voice", interactive=True, allow_custom_value=True)
                    speed = gr.Slider(minimum=0.25, maximum=4.0, step=0.1, label="Speed", value=1.0,
                                      info="Speed of the speech, 1.0 is normal speed")
                    openai_output_format = gr.Dropdown(get_openai_supported_output_formats(), label="Output Format", interactive=True)
                with gr.Row(equal_height=True):
                    instructions = gr.TextArea(label="Voice Instructions", interactive=True, lines=3,
                                               value=get_openai_instructions_example())
                open_ai_tab.select(on_tab_change, inputs=None, outputs=None)
            with gr.Tab("Azure") as azure_tab:
                gr.Markdown("It is expected that user configured: `MS_TTS_KEY` and `MS_TTS_REGION` in the environment variables.")
                with gr.Row(equal_height=True):
                    azure_language = gr.Dropdown(get_azure_supported_languages(), value="en-US", label="Language",
                                               interactive=True, info="Select source language")
                    azure_voice = get_azure_voices_by_language(azure_language.value)
                    azure_output_format = gr.Dropdown(get_azure_supported_output_formats(), label="Output Format", interactive=True,
                                                value="audio-24khz-48kbitrate-mono-mp3", info="Select output format")
                    break_duration = gr.Slider(minimum=1, maximum=5000, step=1, label="Break Duration", value=1250,
                                               info="Break duration in milliseconds. Valid values range from 0 to 5000, default: 1250ms")
                    azure_language.change(
                        fn=get_azure_voices_by_language,
                        inputs=azure_language,
                        outputs=azure_voice,
                    )
                azure_tab.select(on_tab_change, inputs=None, outputs=None)

            with gr.Tab("Edge") as edge_tab:
                with gr.Row(equal_height=True):
                    edge_language = gr.Dropdown(get_edge_tts_supported_language(), value="en-US", label="Language",
                                           interactive=True, info="Select source language")
                    edge_voice = get_edge_voices_by_language(edge_language.value)
                    edge_output_format = gr.Dropdown(get_edge_tts_supported_output_formats(), label="Output Format",
                                                      interactive=True, info="Select output format")
                    proxy = gr.Textbox(label="Proxy", value="", interactive=True, info="Optional proxy server for the TTS provider")
                    edge_voice_rate = gr.Slider(minimum=-50, maximum=100, step=1, label="Voice Rate", value=0,
                                           info="Speaking rate (speed) of the text.")
                    edge_volume = gr.Slider(minimum=-100, maximum=100, step=1, label="Voice Volume", value=0,
                                            info="Volume level of the speaking voice.")
                    edge_pitch = gr.Slider(minimum=-100, maximum=100, step=1, label="Voice Pitch", value=0,
                                           info="Baseline pitch tone for the text.")

                    edge_language.change(
                        fn=get_edge_voices_by_language,
                        inputs=edge_language,
                        outputs=edge_voice,
                    )
                edge_tab.select(on_tab_change, inputs=None, outputs=None)

            with gr.Tab("Piper") as piper_tab:
                piper_tab.select(on_tab_change, inputs=None, outputs=None)
                with gr.Row(equal_height=True):
                    with gr.Column():
                        piper_deployment = gr.Dropdown(["Docker", "Local"], label="Select Piper Deployment", interactive=True)

                        local_group = gr.Group(visible=False)
                        with local_group:
                            piper_executable_path = gr.Textbox(label="Piper executable path", interactive=True)
                            gr.Button("Browse").click(fn=lambda: get_file_path(("Piper executable", "*.exe")), outputs=piper_executable_path)

                        docker_group = gr.Row(visible=True, equal_height=True)
                        with docker_group:
                            piper_docker_image = gr.Textbox(label="Piper Docker Image", value="lscr.io/linuxserver/piper:latest", interactive=True)

                    piper_deployment.change(
                        fn=lambda x: (gr.update(visible=x == "Local"), gr.update(visible=x == "Docker")),
                        inputs=piper_deployment,
                        outputs=[local_group, docker_group]
                    )

                    with gr.Column():
                        with gr.Row(equal_height=True):
                            piper_language = gr.Dropdown(get_piper_supported_languages(), label="Language", value="en_US", interactive=True, info="Select language")
                            piper_voice = gr.Dropdown(get_piper_supported_voices(piper_language.value), label="Voice", interactive=True, info="Select voice")
                        with gr.Row(equal_height=True):
                            piper_quality = gr.Dropdown(get_piper_supported_qualities(piper_language.value, piper_voice.value), label="Quality", interactive=True, info="Select quality")
                            piper_speaker = gr.Dropdown(get_piper_supported_speakers(piper_language.value, piper_voice.value, piper_quality.value), label="Speaker", interactive=True, info="Select speaker if available")

                    piper_language.change(
                        fn=get_piper_supported_voices_gui,
                        inputs=piper_language,
                        outputs=piper_voice,
                    )

                    piper_voice.change(
                        fn=get_piper_supported_qualities_gui,
                        inputs=[piper_language, piper_voice],
                        outputs=piper_quality,
                    )

                    piper_quality.change(
                        fn=get_piper_supported_speakers_gui,
                        inputs=[piper_language, piper_voice, piper_quality],
                        outputs=piper_speaker,
                    )

                    with gr.Column():
                        with gr.Row(equal_height=True):
                            piper_noice_scale = gr.Slider(minimum=0.0, maximum=2.0, step=0.01, label="Audio Noise Scale", value=0.667)
                            piper_noice_w_scale = gr.Slider(minimum=0.0, maximum=2.0, step=0.1, label="Width Noise Scale", value=0.8)
                        with gr.Row(equal_height=True):
                            piper_length_scale = gr.Slider(minimum=0.0, maximum=5.0, step=0.1, label="Audio Length Scale", value=1.0)
                            piper_sentence_silence = gr.Slider(minimum=0.0, maximum=2.0, step=0.1, label="Sentence Silence", value=0.2)
        gr.Markdown("---")
        with gr.Row(equal_height=True):
            gr.Button("Stop").click(
                fn=terminate_audiobook_generator,
                inputs=None,
                outputs=None)
            gr.Button("Start", variant="primary").click(
                fn=process_ui_form,
                inputs=[
                    input_file, output_dir, worker_count, log_level, output_text, preview,
                    search_and_replace_file, title_mode, new_line_mode, chapter_start, chapter_end, remove_endnotes, remove_reference_numbers,
                    model, voices, speed, openai_output_format, instructions,
                    azure_language, azure_voice, azure_output_format, break_duration,
                    edge_language, edge_voice, edge_output_format, proxy, edge_voice_rate, edge_volume, edge_pitch,
                    piper_executable_path, piper_docker_image, piper_language, piper_voice, piper_quality, piper_speaker,
                    piper_noice_scale, piper_noice_w_scale, piper_length_scale, piper_sentence_silence
                ],
                outputs=None)
        with gr.Row():
            log_display = gr.Textbox(label="Log Output", interactive=False, lines=10, max_lines=20)
            gr.Timer(1).tick(fn=read_logs, inputs=log_display, outputs=log_display)

    ui.launch(server_name=config.host, server_port=config.port)