import cv2
import datetime
import os
import sys
import argparse
import time
import math
from ultralytics import YOLO

# Sound alert support on Windows
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

def play_alert_sound():
    if HAS_WINSOUND:
        try:
            # Play the configured Windows warning sound, then a short audible
            # tone so alerts still have an audible signal if the system alias is silent.
            winsound.PlaySound(
                "SystemExclamation",
                winsound.SND_ALIAS | winsound.SND_ASYNC
            )
            winsound.Beep(1500, 350)
        except RuntimeError as error:
            print(f"[WARNING] Could not play alert sound: {error}")
    else:
        print("[WARNING] Sound alerts are unavailable because winsound is not supported on this platform.")


def main():
    parser = argparse.ArgumentParser(description="Real-time gun-only detection with snapshot logging and alerts")
    parser.add_argument("-m", "--model", type=str, default=None, help="Path to a YOLO gun detection model (defaults to gun_detector.pt beside this script)")
    parser.add_argument("-v", "--video", type=str, default=None, help="Path to video file (defaults to webcam)")
    parser.add_argument("-o", "--output", type=str, default="detections", help="Directory to save detected gun snapshots")
    parser.add_argument("--cooldown", type=float, default=2.0, help="Minimum seconds between snapshot recordings")
    parser.add_argument("--confidence", type=float, default=0.6, help="Minimum gun confidence from 0 to 1")
    parser.add_argument("--no-sound", action="store_true", help="Disable audio alarm beep")
    args = parser.parse_args()

    if not math.isfinite(args.cooldown) or args.cooldown < 0:
        parser.error("--cooldown must be a finite, non-negative number")
    if not math.isfinite(args.confidence) or not 0 <= args.confidence <= 1:
        parser.error("--confidence must be between 0 and 1")

    # Create output directory for detections if it doesn't exist
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)
    print(f"[INFO] Detection snapshots will be saved to: '{output_dir}'")

    # Load a gun-specific YOLO model. The included model also has a knife class,
    # so only its class explicitly named "gun" is allowed through.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = args.model or os.path.join(script_dir, "gun_detector.pt")
    if not os.path.exists(model_path):
        print(f"[ERROR] YOLO model file not found: '{model_path}'")
        sys.exit(1)

    try:
        gun_model = YOLO(model_path)
    except Exception as error:
        print(f"[ERROR] Failed to load YOLO model from '{model_path}': {error}")
        sys.exit(1)

    gun_class_ids = [
        int(class_id)
        for class_id, class_name in gun_model.names.items()
        if str(class_name).strip().lower() in {"gun", "firearm"}
    ]
    if not gun_class_ids:
        print(f"[ERROR] Model has no class named 'gun' or 'firearm'. Available classes: {gun_model.names}")
        sys.exit(1)
    print(f"[INFO] Loaded gun model from: {model_path}")
    print(f"[INFO] Detecting only class(es): {[gun_model.names[class_id] for class_id in gun_class_ids]}")

    # Initialize video capture source (webcam or video file)
    if args.video:
        if not os.path.exists(args.video):
            print(f"[ERROR] Video file not found: {args.video}")
            sys.exit(1)
        camera = cv2.VideoCapture(args.video)
        print(f"[INFO] Opening video file: {args.video}")
    else:
        camera = cv2.VideoCapture(0)
        print("[INFO] Starting webcam stream (Camera 0)...")

    if not camera.isOpened():
        print("[ERROR] Could not open video source.")
        camera.release()
        sys.exit(1)

    print("[INFO] Press 'q' or 'ESC' in the feed window to exit.")

    last_snapshot_time = 0
    last_sound_time = 0
    snapshot_saved_notice_until = 0

    try:
        while True:
            ret, frame = camera.read()
            if not ret or frame is None:
                print("[INFO] Video stream ended or frame unavailable.")
                break

            # Resize frame for faster processing while preserving its aspect ratio.
            frame_height, frame_width = frame.shape[:2]
            resized_height = round(frame_height * 650 / frame_width)
            interpolation = cv2.INTER_AREA if frame_width > 650 else cv2.INTER_LINEAR
            frame = cv2.resize(frame, (650, resized_height), interpolation=interpolation)
            # Ask YOLO for gun classes only; non-gun classes cannot trigger alerts.
            result = gun_model.predict(
                frame,
                conf=args.confidence,
                classes=gun_class_ids,
                verbose=False
            )[0]
            guns = []
            if result.boxes is not None:
                for box in result.boxes.xyxy.cpu().tolist():
                    x1, y1, x2, y2 = (int(value) for value in box)
                    guns.append((x1, y1, x2 - x1, y2 - y1))

            gun_count = len(guns)
            current_time = time.time()
            now_dt = datetime.datetime.now()
            timestamp_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

            # Draw bounding boxes around accepted gun detections.
            for (x, y, w, h) in guns:
                # Draw red bounding box
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                # Draw tag header box
                cv2.rectangle(frame, (x, max(0, y - 25)), (x + w, y), (0, 0, 255), cv2.FILLED)
                cv2.putText(
                    frame, 
                    f"GUN DETECTED ({gun_count})", 
                    (x + 5, y - 7), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, 
                    (255, 255, 255), 
                    2
                )

            # When gun is spotted
            if gun_count > 0:
                # Console Alert Message with timestamp and gun count
                print(f"[ALERT]  {timestamp_str} | THREAT DETECTED: {gun_count} Gun(s) Spotted in feed!")

                # Avoid blocking or playing a sound on every video frame.
                if not args.no_sound and current_time - last_sound_time >= 1.0:
                    play_alert_sound()
                    last_sound_time = current_time

                # Check snapshot cooldown interval
                if (current_time - last_snapshot_time) >= args.cooldown:
                    # Generate filename with date and time
                    date_time_file_str = now_dt.strftime("%Y%m%d_%H%M%S")
                    snapshot_filename = f"gun_alert_{date_time_file_str}_count{gun_count}.jpg"
                    snapshot_path = os.path.join(output_dir, snapshot_filename)

                    # Save image snapshot to file
                    if cv2.imwrite(snapshot_path, frame):
                        snapshot_saved_notice_until = current_time + 1.5
                        print(f"[SUCCESS]  Saved detection snapshot: '{snapshot_path}'")
                    else:
                        print(f"[ERROR] Could not save detection snapshot: '{snapshot_path}'")
                    last_snapshot_time = current_time

            # UI Overlay Status Banner
            if gun_count > 0:
                status_text = f"[ALERT] {gun_count} GUN(S) SPOTTED!"
                status_color = (0, 0, 255)  # Red
                banner_width = 380
            else:
                status_text = "[NORMAL] System Monitoring"
                status_color = (0, 255, 0)  # Green
                banner_width = 310

            # Top bar status background
            cv2.rectangle(frame, (10, 10), (10 + banner_width, 45), (0, 0, 0), cv2.FILLED)
            cv2.putText(frame, status_text, (20, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)

            # Display Snapshot Saved Notice on Screen
            if current_time < snapshot_saved_notice_until:
                cv2.rectangle(frame, (10, 50), (320, 80), (0, 140, 255), cv2.FILLED)  # Orange tag
                cv2.putText(frame, " Snapshot Saved to File!", (20, 71), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            # Bottom timestamp overlay
            cv2.putText(
                frame, 
                f"TIME: {timestamp_str}", 
                (10, frame.shape[0] - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, 
                (255, 255, 255), 
                1
            )

            # Display feed window
            cv2.imshow("Security Feed - Gun Detection System", frame)

            # Keypress control ('q' or ESC key to quit)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                print("[INFO] Exit signal received.")
                break

    except KeyboardInterrupt:
        print("[INFO] Interrupted by user.")
    finally:
        camera.release()
        cv2.destroyAllWindows()
        print("[INFO] Video feed closed and resources released.")

if __name__ == "__main__":
    main()
