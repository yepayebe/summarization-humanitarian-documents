import sys
import os
import hashlib
import struct
import subprocess
import collections
import spacy
import codecs
import re
import numpy as np
from random import shuffle
import tensorflow as tf
from tensorflow.core.example import example_pb2


dm_single_close_quote = u'\u2019' # unicode
dm_double_close_quote = u'\u201d'
END_TOKENS = ['.', '!', '?', '...', "'", "`", '"', dm_single_close_quote, dm_double_close_quote, ")"] # acceptable ways to end a sentence

# We use these to separate the summary sentences in the .bin datafiles
SENTENCE_START = '<s>'
SENTENCE_END = '</s>'


docs_processed_en_dir = "/idiap/temp/jbello/summarization-humanitarian-documents/data/collection/docs_with_summaries_processed/en/"
docs_processed_fr_dir = "/idiap/temp/jbello/summarization-humanitarian-documents/data/collection/docs_with_summaries_processed/fr/"
docs_processed_es_dir = "/idiap/temp/jbello/summarization-humanitarian-documents/data/collection/docs_with_summaries_processed/es/"
chunks_en_dir = os.path.join(docs_processed_en_dir, "chunked")
chunks_fr_dir = os.path.join(docs_processed_fr_dir, "chunked")
chunks_es_dir = os.path.join(docs_processed_es_dir, "chunked")


VOCAB_SIZE = 200000
CHUNK_SIZE = 1000 # num examples per chunk, for the chunked data


def chunk_file(set_name,files_dir, chunks_dir):
  in_file = str(files_dir)+'%s.bin' % set_name
  reader = open(in_file, "rb")
  chunk = 0
  finished = False
  while not finished:
    chunk_fname = os.path.join(chunks_dir, '%s_%03d.bin' % (set_name, chunk)) # new chunk
    with open(chunk_fname, 'wb') as writer:
      for _ in range(CHUNK_SIZE):
        len_bytes = reader.read(8)
        if not len_bytes:
          finished = True
          break
        str_len = struct.unpack('q', len_bytes)[0]
        example_str = struct.unpack('%ds' % str_len, reader.read(str_len))[0]
        writer.write(struct.pack('q', str_len))
        writer.write(struct.pack('%ds' % str_len, example_str))
      chunk += 1


def chunk_all(files_dir,chunks_dir):
  # Make a dir to hold the chunks
  if not os.path.isdir(chunks_dir):
    os.mkdir(chunks_dir)
  # Chunk the data
  for set_name in ['train', 'val', 'test']:
    print ("Splitting "+str(set_name) +" data into chunks...") 
    chunk_file(set_name,files_dir, chunks_dir)
  print ("Saved chunked data in " + str(chunks_dir))


def read_directory(directory, name_text = '.txt'):
    '''Read documents in directory. The type of text to read can be precised, 
    given the name of the text (whether is document/summary)'''
    filenames = []
    documents = []
    for file in os.listdir(directory):
        filename = str(file)
        if (name_text) in filename:
            with codecs.open(os.path.join(directory,filename),encoding="utf-8") as f:
                filenames.append(filename)
                documents.append(f.read())
    return filenames, documents

def extract_id(string_with_id):
    if type(string_with_id) == list:
        id_doc = []
        for i in range (0,len(string_with_id)):
            id_doc.append(re.findall(r'\d+',string_with_id[i])[0])
        return id_doc
    elif(type(string_with_id) == str):
        return re.findall(r'\d+',string_with_id)[0]

def save_documents(idx, documents, relative_path):
    for i in range(0,len(documents)):
        complete_doc_name = os.path.join(relative_path,'document.'+ str(idx[i]) +'.txt')
        with codecs.open(complete_doc_name,'w', encoding = 'utf-8') as f:
            f.write(documents[i])

def partition(data_directory, name_text, language_partition = None, language = 'en', train_prop = 0.7, val_prop = 0.1, test_prop = 0.2):
    if language_partition == None:
        '''Partition 70.10.20 by default'''
        fn, doc = read_directory(data_directory, name_text)
        ids = extract_id(fn)
    else:
        with open(language_partition) as json_file:
            ids = json.load(json_file)
        if language == 'en':
            ids = ids[0]
        elif language == 'es':
            ids = ids[1]
        elif language == 'fr':
            ids = ids[2]
        elif language == 'ar':
            ids = ids[3]
        else:
            print('not partition find for such a language!')
    #randomize order
    shuffle(ids)
    #make partition
    train_limit = int(len(ids)*train_prop)
    val_limit = train_limit + (int(len(ids)*val_prop))
    test_limit = len(ids)
    seq = [train_limit,val_limit,test_limit]
    result = []
    for i in range(0,len(seq)):
        chunk = []
        if (i == 0):
            for j in range(0, train_limit):
                chunk.append(ids[j])
        else:
            for j in range (seq[i-1], seq[i]):
                chunk.append(ids[j])
        result.append(chunk)
    return result

def tokenize_documents(documents_dir, tokenized_documents_dir, language):
  """Maps a whole directory of .txt files to a tokenized version using Spacy Tokenizer"""
  
  print ("Preparing to tokenize %s to %s..." % (documents_dir, tokenized_documents_dir))
  fn, documents = read_directory(documents_dir)
  ids = extract_id(fn)

  if (language == 'en'):
      nlp = spacy.load('en_core_web_sm')
  elif (language == 'fr'):
      nlp = spacy.load('fr_core_news_sm')
  elif (language == 'es'):
      nlp = spacy.load('es_core_news_sm')
  else:
      raise Exception("Language not supported")

  tok_doc = []
  for d in documents:
      if (len(d) > 1000000):
          nlp.max_length = len(d) + 1
      doc = nlp(d)
      tokens = [token.text for token in doc]
      tok_doc.append(' '.join(tokens))

  save_documents(ids,tok_doc,tokenized_documents_dir)

  # Check that the tokenized documents directory contains the same number of files as the original directory
  list_orig = os.listdir(documents_dir)
  num_orig = np.sum(['document.' in i for i in list_orig])
  list_tokenized = os.listdir(tokenized_documents_dir)
  num_tokenized = np.sum(['document.' in i for i in list_tokenized])
  if num_orig != num_tokenized:
    raise Exception("The tokenized stories directory %s contains %i files, but it should contain the same number as %s (which has %i files). Was there an error during tokenization?" % (tokenized_documents_dir, num_tokenized, documents_dir, num_orig))
  print ("Successfully finished tokenizing %s to %s.\n" % (documents_dir, tokenized_documents_dir))


def read_text_file(text_file):
  lines = []
  text_file = text_file.split('\n\n')
  for line in text_file:
      lines.append(line.strip())
  return text_file


def fix_missing_period(line):
  """Adds a period to a line that is missing a period"""
  if "@highlight" in line: return line
  if line=="": return line
  if line[-1] in END_TOKENS: return line
  # print line[-1]
  return line + " ."


def get_art_abs(story_file):
  lines = read_text_file(story_file)

  # Lowercase everything
  lines = [line.lower() for line in lines]

  # Put periods on the ends of lines that are missing them (this is a problem in the dataset because many image captions don't end in periods; consequently they end up in the body of the article as run-on sentences)
  lines = [fix_missing_period(line) for line in lines]

  # Separate out article and abstract sentences
  article_lines = []
  highlights = []
  next_is_highlight = False
  for idx,line in enumerate(lines):
    if line == "":
      continue # empty line
    elif line.startswith(" @highlight"):
      next_is_highlight = True
    elif next_is_highlight:
      highlights.append(line)
    else:
      article_lines.append(line)
  # Make article into a single string
  article = ' '.join(article_lines)

  # Make abstract into a signle string, putting <s> and </s> tags around the sentences
  abstract = ' '.join(["%s %s %s" % (SENTENCE_START, sent, SENTENCE_END) for sent in highlights])

  return article, abstract


def write_to_bin(partition_file, part, tokenized_directory, out_file, makevocab=False):
  """Reads the tokenized files, and partition division, and writes them to a out_file."""

  print("Reading files in partition ", str(part))
  if (part == 'train'):
      partition = partition_file[0]
  elif (part == 'val'):
      partition = partition_file[1]
  elif (part == 'test'):
      partition = partition_file[2]
  else:
      print("Error: Please provide a valid partition (i.e. train, val or test)")

  filename = []
  docum = []
  for i in range(0,len(partition)):
      temp_fn, temp_d = read_directory(tokenized_directory, 'document.'+partition[i]+'.txt')
      #we are searching element by element(we don't want a list, we want the string name)
      filename.append(temp_fn[0])
      docum.append(temp_d[0])                                                                                                 

  num_documents = len(docum)

  if (makevocab):
    vocab_counter = collections.Counter()

  with open(out_file, 'wb') as writer:
    for idx,s in enumerate(filename):
      #if idx % 1000 == 0:
        #print "Writing document %i of %i; %.2f percent done" % (idx, num_documents float(idx)*100.0/float(num_documents))
        
      # Get the strings to write to .bin file
      article, abstract = get_art_abs(docum[idx].encode('raw_unicode_escape'))

      # Write to tf.Example
      tf_example = example_pb2.Example()
      tf_example.features.feature['article'].bytes_list.value.extend([article])
      tf_example.features.feature['abstract'].bytes_list.value.extend([abstract])
      tf_example_str = tf_example.SerializeToString()
      str_len = len(tf_example_str)
      writer.write(struct.pack('q', str_len))
      writer.write(struct.pack('%ds' % str_len, tf_example_str))

      # Write the vocab to file, if applicable
      if (makevocab):
        art_tokens = article.split(' ')
        abs_tokens = abstract.split(' ')
        abs_tokens = [t for t in abs_tokens if t not in [SENTENCE_START, SENTENCE_END]] # remove these tags from vocab
        tokens = art_tokens + abs_tokens
        tokens = [t.strip() for t in tokens] # strip
        tokens = [t for t in tokens if t!=""] # remove empty
        vocab_counter.update(tokens)

  print ("Finished writing file"+str(out_file)+"\n")

  # write vocab to file
  if (makevocab):
    print ("Writing vocab file...")
    with open(os.path.join(tokenized_directory, "vocab.txt"), 'w') as writer:
      for word, count in vocab_counter.most_common(VOCAB_SIZE):
        writer.write(word + ' ' + str(count) + '\n')
    print ("Finished writing vocab file")


if __name__ == '__main__':
  if len(sys.argv) != 4:
    print ("USAGE: python make_datafiles.py <docs_with_summaries_en_dir> <docs_with_summaries_fr_dir> <docs_with_summaries_es_dir>")
    sys.exit()
  docs_en_dir = sys.argv[1]
  docs_fr_dir = sys.argv[2]
  docs_es_dir = sys.argv[3]

  # Create some new directories
  if not os.path.exists(docs_processed_en_dir): os.makedirs(docs_processed_en_dir)
  if not os.path.exists(docs_processed_fr_dir): os.makedirs(docs_processed_fr_dir)
  if not os.path.exists(docs_processed_es_dir): os.makedirs(docs_processed_es_dir)

  # Run tokenizer on documents dirs, outputting to tokenized documents directories
  #tokenize_documents(docs_en_dir, docs_processed_en_dir,'en')
  #tokenize_documents(docs_fr_dir, docs_processed_fr_dir,'fr')
  tokenize_documents(docs_es_dir, docs_processed_es_dir,'es')

  # Partition files in train, validation and test
  #partition_en = partition(docs_processed_en_dir,'document.')
  #partition_fr = partition(docs_processed_fr_dir,'document.')
  partition_es = partition(docs_processed_es_dir,'document.')
  
  # Read the tokenized files, do a little postprocessing then write to bin files
  #write_to_bin(partition_en, 'test',docs_processed_en_dir, os.path.join(docs_processed_en_dir, "test.bin"))
  #write_to_bin(partition_en, 'val', docs_processed_en_dir, os.path.join(docs_processed_en_dir, "val.bin"))
  #write_to_bin(partition_en, 'train', docs_processed_en_dir, os.path.join(docs_processed_en_dir, "train.bin"), makevocab=True)

  #write_to_bin(partition_fr, 'test',docs_processed_fr_dir, os.path.join(docs_processed_fr_dir, "test.bin"))
  #write_to_bin(partition_fr, 'val', docs_processed_fr_dir, os.path.join(docs_processed_fr_dir, "val.bin"))
  #write_to_bin(partition_fr, 'train', docs_processed_fr_dir, os.path.join(docs_processed_fr_dir, "train.bin"), makevocab=True)

  write_to_bin(partition_es, 'test', docs_processed_es_dir, os.path.join(docs_processed_es_dir, "test.bin"))
  write_to_bin(partition_es, 'val', docs_processed_es_dir, os.path.join(docs_processed_es_dir, "val.bin"))
  write_to_bin(partition_es, 'train', docs_processed_es_dir, os.path.join(docs_processed_es_dir, "train.bin"), makevocab=True)

  # Chunk the data. This splits each of train.bin, val.bin and test.bin into smaller chunks, each containing e.g. 1000 examples, and saves them in e.g. data_processed_en_dir/chunks
  chunk_all(docs_processed_en_dir,chunks_en_dir)
  #chunk_all(docs_processed_fr_dir,chunks_fr_dir)
  #chunk_all(docs_processed_es_dir,chunks_es_dir)
