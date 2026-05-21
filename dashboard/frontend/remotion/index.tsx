import { Composition, registerRoot } from "remotion";
import {
  PRODUCT_HUNT_DEMO_DURATION,
  PRODUCT_HUNT_DEMO_FPS,
  ProductHuntDemo,
} from "../src/remotion/ProductHuntDemo";

const RemotionRoot = () => (
  <Composition
    id="PlatoProductHuntDemo"
    component={ProductHuntDemo}
    durationInFrames={PRODUCT_HUNT_DEMO_DURATION}
    fps={PRODUCT_HUNT_DEMO_FPS}
    width={1920}
    height={1080}
  />
);

registerRoot(RemotionRoot);
