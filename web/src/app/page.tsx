import Navbar from "@/components/Navbar";
import Hero from "@/components/Hero";
import OnDevice from "@/components/OnDevice";
import HowItWorks from "@/components/HowItWorks";
import Architecture from "@/components/Architecture";
import Demo from "@/components/Demo";
import Probing from "@/components/Probing";
import Cost from "@/components/Cost";
import Honesty from "@/components/Honesty";
import CallToAction from "@/components/CallToAction";
import Footer from "@/components/Footer";

export default function Home() {
  return (
    <>
      <Navbar />
      <main id="main">
        <Hero />
        <OnDevice />
        <Demo />
        <HowItWorks />
        <Architecture />
        <Probing />
        <Cost />
        <Honesty />
        <CallToAction />
      </main>
      <Footer />
    </>
  );
}
