import { useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import Icon from "./Icon";

/** A horizontally scrolling shelf with arrow buttons, Netflix-style. */
export default function Row({ title, to, children }: { title: string; to?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const scroll = (dir: number) => ref.current?.scrollBy({ left: dir * ref.current.clientWidth * 0.85, behavior: "smooth" });
  return (
    <section className="row">
      <div className="row-head">
        <h2>{title}</h2>
        {to && <Link to={to} className="row-more">See all <Icon name="chevronRight" size={16} /></Link>}
      </div>
      <div className="row-wrap">
        <button className="row-arrow left" onClick={() => scroll(-1)} aria-label="Scroll left"><Icon name="chevronLeft" size={28} /></button>
        <div className="row-track" ref={ref}>{children}</div>
        <button className="row-arrow right" onClick={() => scroll(1)} aria-label="Scroll right"><Icon name="chevronRight" size={28} /></button>
      </div>
    </section>
  );
}
