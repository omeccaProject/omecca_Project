import face_recognition, cv2, numpy as np, os

img = cv2.imdecode(np.fromfile(os.path.join('known_faces', 'W001_이시헌_2.jpg'), np.uint8), 1)
rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
locs = face_recognition.face_locations(rgb, model='cnn', number_of_times_to_upsample=1)
emb = face_recognition.face_encodings(rgb, locs)[0]

for name in ['김관용', '김준호', '장성혁', '박지원']:
    path = os.path.join('others', f'{name}.jpg')
    o_img = cv2.imdecode(np.fromfile(path, np.uint8), 1)
    o_rgb = cv2.cvtColor(o_img, cv2.COLOR_BGR2RGB)
    o_locs = face_recognition.face_locations(o_rgb, model='hog')
    o_emb = face_recognition.face_encodings(o_rgb, o_locs)[0]
    dist = face_recognition.face_distance([emb], o_emb)[0]
    print(name, '->', round(float(dist), 4))