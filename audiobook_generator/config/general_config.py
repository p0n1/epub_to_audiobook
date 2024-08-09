class GeneralConfig:
    def __init__(self, args):
        # General arguments
        self.input_file = args.input_file
        self.output_folder = args.output_folder
        self.preview = args.preview
        self.output_text = args.output_text
        self.log = args.log
        self.no_prompt = args.no_prompt
        self.title_mode = args.title_mode
        self.item_types = args.item_type

        # Book parser specific arguments
        self.newline_mode = args.newline_mode
        self.chapter_start = args.chapter_start
        self.chapter_end = args.chapter_end
        self.remove_endnotes = args.remove_endnotes

        # TTS provider: common arguments
        self.tts = args.tts
        self.language = args.language
        self.voice_name = args.voice_name
        self.output_format = args.output_format
        self.model_name = args.model_name

        # TTS provider: Azure & Edge TTS specific arguments
        self.break_duration = args.break_duration

        # TTS provider: Edge specific arguments
        self.voice_rate = args.voice_rate
        self.voice_volume = args.voice_volume
        self.voice_pitch = args.voice_pitch
        self.proxy = args.proxy

        # TTS provider: Piper specific arguments
        self.path_to_piper = args.path_to_piper
        self.piper_voice_folder = args.piper_voice_folder
        self.piper_length_scale = args.piper_length_scale
        self.piper_sentence_silence = args.piper_sentence_silence
        self.piper_quality = args.piper_quality

    def __str__(self):
        return ', '.join(f"{key}={value}" for key, value in self.__dict__.items())
