import { Composition } from "remotion";
import { RoboMedicDemo } from "./RoboMedicDemo";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition id="RoboMedicDemo" component={RoboMedicDemo} durationInFrames={3600} fps={30} width={1920} height={1080} />
  );
};
