import os
import sys

import numpy as np

# add mindocr root path, and import postprocess from mindocr
mindocr_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))
sys.path.insert(0, mindocr_path)

from mindocr.postprocess import rec_postprocess  # noqa


#  TODO: unify RecCTCLabelDecode with with trained side
class RecCTCLabelDecode(rec_postprocess.RecCTCLabelDecode):
    """CTCLabelDecode, adapted to paddleocr"""

    def __init__(
        self,
        character_dict_path=None,
        use_space_char=False,
        blank_at_last=True,
        lower=False,
        # for paddleocr
        use_redundant_space_char=False,
        **kwargs,
    ):
        self.space_idx = None
        self.lower = lower

        # read dict
        if character_dict_path is None:
            char_list = [c for c in "0123456789abcdefghijklmnopqrstuvwxyz"]
            self.lower = True
            print("INFO: The character_dict_path is None, model can only recognize number and lower letters")
        else:
            # parse char dictionary
            char_list = []
            with open(character_dict_path, "r") as f:
                for line in f:
                    c = line.rstrip("\n\r")
                    char_list.append(c)
        # add space char if set
        if use_space_char:
            if " " not in char_list:
                char_list.append(" ")
            self.space_idx = len(char_list) - 1
        else:
            if " " in char_list:
                print(
                    f"WARNING: The dict still contains space char in dict although use_space_char is set to be False, \
                    because the space char is coded in the dictionary file {character_dict_path}"
                )

        if use_redundant_space_char:
            char_list.append(" ")  # paddleOCR rec models need two space char

        self.num_valid_chars = len(char_list)  # the number of valid chars (including space char if used)

        # add blank token for padding
        if blank_at_last:
            # the index of a char in dict is [0, num_chars-1], blank index is set to num_chars
            char_list.append("<PAD>")
            self.blank_idx = self.num_valid_chars
        else:
            char_list = ["<PAD>"] + char_list
            self.blank_idx = 0

        self.ignore_indices = [self.blank_idx]

        self.character = {idx: c for idx, c in enumerate(char_list)}

        self.num_classes = len(self.character)

    def __call__(self, preds):
        """
        Args:
            preds (np.ndarray): containing prediction tensor in shape [BS, W, num_classes]
        Return:
            texts (List[Tuple]): list of string
        """
        preds = preds[0] if isinstance(preds, (tuple, list)) else preds

        if len(preds.shape) == 3:
            pred_indices = preds.argmax(axis=-1)
        else:
            pred_indices = preds

        texts, confs = self.decode(pred_indices, remove_duplicate=True)

        return {"texts": texts, "confs": confs}


class ViTSTRLabelDecode(rec_postprocess.RecCTCLabelDecode):
    def __init__(
        self,
        character_dict_path=None,
        use_space_char=False,
        use_redundant_space_char=False,
        blank_at_last=True,
        **kwargs,
    ):
        super().__init__(character_dict_path, use_space_char, use_redundant_space_char, blank_at_last, **kwargs)
        char_list = list(self.character.values())[1:]
        char_list = ["<s>", "</s>"] + char_list
        self.character = {idx: c for idx, c in enumerate(char_list)}
        self.num_classes = len(self.character)

    def decode(self, char_indices, prob=None, remove_duplicate=False):
        texts = []
        confs = []
        batch_size = len(char_indices)
        for batch_idx in range(batch_size):
            char_list = []
            conf_list = []
            for idx in range(len(char_indices[batch_idx])):
                try:
                    char_idx = self.character[int(char_indices[batch_idx][idx])]
                except Exception:
                    continue
                if char_idx == "</s>":
                    break
                char_list.append(char_idx)
                conf_list.append(prob[batch_idx][idx]) if prob is not None else conf_list.append(1)
            texts.append("".join(char_list).lower())
            confs.append(np.mean(conf_list))
        return texts, confs

    def __call__(self, preds):
        preds = preds[0] if isinstance(preds, (tuple, list)) else preds
        preds = preds[:, 1:]
        pred_indices = preds.argmax(axis=-1)
        preds_prob = preds.max(axis=2)
        texts, confs = self.decode(pred_indices, preds_prob, remove_duplicate=True)
        return {"texts": texts, "confs": confs}
